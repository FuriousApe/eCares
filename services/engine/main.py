"""Engine worker entrypoint (`ROLE=engine`).

1. Loads `seeds/programs/*.yaml` and upserts them via `UpsertPrograms`.
2. Reads them back via `ListPrograms` so program state genuinely round-trips
   through the Data Service (CLAUDE.md decision #9), not just the local YAML.
3. Consumes `patient.changed` off Kafka: fetch snapshot, evaluate, save.
   Retries a failing patient a few times in-process; if still failing, hands
   the raw message to the DLQ topic and commits anyway so one bad patient
   never blocks the partition. See ASSUMPTIONS.md for the exact message
   shape this assumes and the idempotency-key formula.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, timezone

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import ConsumerRecord

from libs.common.grpc_client import call_metadata, data_service_async_stub
from libs.common.grpc_gen import dataservice_pb2
from libs.common.logging import configure_logging
from libs.common.settings import Settings, get_settings
from services.engine import evaluator
from services.engine.program_loader import from_proto_program, load_programs, to_proto_program

logger = logging.getLogger("engine")


# ---------------------------------------------------------------------------
# proto <-> evaluator dataclass conversion (kept out of evaluator.py so the
# pure core has no proto dependency)
# ---------------------------------------------------------------------------


def _snapshot_from_proto(resp: dataservice_pb2.GetPatientSnapshotResponse) -> evaluator.PatientSnapshot:
    return evaluator.PatientSnapshot(
        patient_id=resp.patient.patient_id,
        age=resp.patient.age,
        diagnoses=[
            evaluator.Diagnosis(icd_code=d.icd_code, diagnosed_date=date.fromisoformat(d.diagnosed_date))
            for d in resp.diagnoses
        ],
        labs=[
            evaluator.LabResult(
                test_name=lab.test_name,
                result_value=lab.result_value,
                result_date=date.fromisoformat(lab.result_date),
            )
            for lab in resp.labs
        ],
        encounters=[
            evaluator.Encounter(
                specialty=e.specialty,
                encounter_date=date.fromisoformat(e.encounter_date),
                is_upcoming=e.is_upcoming,
            )
            for e in resp.encounters
        ],
    )


def _need_to_proto(need: evaluator.NeedResult) -> dataservice_pb2.NeedResult:
    kwargs: dict = dict(
        specialty=need.specialty,
        cadence_days=need.cadence_days,
        has_upcoming=need.has_upcoming,
        decision=need.decision,
    )
    if need.last_visit_date is not None:
        kwargs["last_visit_date"] = need.last_visit_date.isoformat()
    if need.due_date is not None:
        kwargs["due_date"] = need.due_date.isoformat()
    if need.next_check_candidate is not None:
        kwargs["next_check_candidate"] = need.next_check_candidate.isoformat()
    return dataservice_pb2.NeedResult(**kwargs)


def _program_result_to_proto(result: evaluator.ProgramResult) -> dataservice_pb2.ProgramResult:
    kwargs: dict = dict(
        program_id=result.program_id,
        program_version=result.program_version,
        eligible=result.eligible,
        needs=[_need_to_proto(n) for n in result.needs],
    )
    if result.tier is not None:
        kwargs["tier"] = result.tier
    if result.tier_recheck_at is not None:
        kwargs["tier_recheck_at"] = result.tier_recheck_at.isoformat()
    return dataservice_pb2.ProgramResult(**kwargs)


def _earliest_next_eval_at(results: list[evaluator.ProgramResult]) -> str:
    """The earliest future date any answer could flip, from what the engine
    alone knows (per-need `next_check_candidate` and `tier_recheck_at`). The
    Data Service is the one that folds in decline snoozes on top of this
    (see the proto's comment on `NeedResult.next_check_candidate`) -- this is
    a candidate, not the final word. Empty string when nothing here can flip
    on its own (e.g. patient ineligible everywhere, or every need is a
    referral/no-history case with no triggering date)."""
    candidates: list[date] = []
    for result in results:
        if result.tier_recheck_at is not None:
            candidates.append(result.tier_recheck_at)
        for need in result.needs:
            if need.next_check_candidate is not None:
                candidates.append(need.next_check_candidate)
    return min(candidates).isoformat() if candidates else ""


def _build_save_request(
    patient_id: str, idempotency_key: str, results: list[evaluator.ProgramResult]
) -> dataservice_pb2.SaveEvaluationResultRequest:
    return dataservice_pb2.SaveEvaluationResultRequest(
        patient_id=patient_id,
        idempotency_key=idempotency_key,
        program_results=[_program_result_to_proto(r) for r in results],
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        next_eval_at=_earliest_next_eval_at(results),
    )


# ---------------------------------------------------------------------------
# Kafka message shape (see ASSUMPTIONS.md)
# ---------------------------------------------------------------------------


def extract_patient_id(msg: ConsumerRecord) -> str:
    """Value is expected to be UTF-8 JSON, either `{"patient_id": "..."}` or
    a bare JSON string. Falls back to the message key, then the raw value
    bytes, decoded as UTF-8, if the value isn't parseable JSON -- the outbox
    relay's exact payload shape is another agent's code, built concurrently."""
    if msg.value:
        try:
            parsed = json.loads(msg.value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict) and "patient_id" in parsed:
            return str(parsed["patient_id"])
        if isinstance(parsed, str):
            return parsed
    if msg.key:
        return msg.key.decode("utf-8")
    if msg.value:
        return msg.value.decode("utf-8")
    raise ValueError("Kafka message has neither a usable value nor key for patient_id")


# ---------------------------------------------------------------------------
# Per-message processing
# ---------------------------------------------------------------------------


async def _evaluate_and_save(
    stub, patient_id: str, programs: list[evaluator.ProgramDefinition], settings: Settings
) -> None:
    as_of_date = settings.effective_as_of_date()
    snapshot_resp = await stub.GetPatientSnapshot(
        dataservice_pb2.GetPatientSnapshotRequest(patient_id=patient_id, as_of_date=as_of_date.isoformat()),
        metadata=call_metadata(),
    )
    snapshot = _snapshot_from_proto(snapshot_resp)
    results = evaluator.evaluate_patient(
        snapshot, programs, as_of_date, frozenset(settings.primary_care_specialty_set)
    )
    idempotency_key = hashlib.sha256(f"{patient_id}:{snapshot_resp.snapshot_hash}".encode()).hexdigest()
    request = _build_save_request(patient_id, idempotency_key, results)
    await stub.SaveEvaluationResult(request, metadata=call_metadata())


async def process_message(
    stub,
    msg: ConsumerRecord,
    programs: list[evaluator.ProgramDefinition],
    settings: Settings,
    producer: AIOKafkaProducer,
) -> None:
    patient_id = extract_patient_id(msg)
    last_exc: Exception | None = None
    for attempt in range(1, settings.kafka_max_retries + 1):
        try:
            await _evaluate_and_save(stub, patient_id, programs, settings)
            return
        except Exception as exc:  # noqa: BLE001 -- retry any failure, then DLQ
            last_exc = exc
            logger.warning(
                "evaluation attempt %s/%s failed for patient %s: %s",
                attempt,
                settings.kafka_max_retries,
                patient_id,
                exc,
            )
            if attempt < settings.kafka_max_retries:
                await asyncio.sleep(0.5 * attempt)

    logger.error(
        "patient %s failed %s attempts, sending to DLQ topic %s: %s",
        patient_id,
        settings.kafka_max_retries,
        settings.kafka_topic_dlq,
        last_exc,
    )
    await producer.send_and_wait(settings.kafka_topic_dlq, key=msg.key, value=msg.value)


# ---------------------------------------------------------------------------
# Startup and consumer loop
# ---------------------------------------------------------------------------


async def load_and_upsert_programs(stub, settings: Settings) -> list[evaluator.ProgramDefinition]:
    programs = load_programs(settings.programs_dir)
    await stub.UpsertPrograms(
        dataservice_pb2.UpsertProgramsRequest(programs=[to_proto_program(p) for p in programs]),
        metadata=call_metadata(),
    )
    listed = await stub.ListPrograms(dataservice_pb2.ListProgramsRequest(), metadata=call_metadata())
    active = [from_proto_program(p) for p in listed.items if p.active]
    if not active:
        raise RuntimeError("ListPrograms returned no active programs after UpsertPrograms")
    return active


async def _run() -> None:
    configure_logging("engine")
    settings = get_settings()
    stub = await data_service_async_stub(settings.data_service_target)

    programs = await load_and_upsert_programs(stub, settings)
    logger.info("loaded %s active program(s): %s", len(programs), [p.program_id for p in programs])

    consumer = AIOKafkaConsumer(
        settings.kafka_topic_patient_changed,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await consumer.start()
    await producer.start()
    try:
        async for msg in consumer:
            await process_message(stub, msg, programs, settings, producer)
            await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
