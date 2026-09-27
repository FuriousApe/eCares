"""Concurrency: 20 parallel `SaveEvaluationResult` calls for the SAME
patient, each independently deciding a task should exist for one
(program, specialty) key, must still leave exactly one open task for that
key. This is what the `open_key` unique index (plus the `patient_eval_state`
row lock serializing evaluations of one patient) actually proves, and it's a
MySQL-only guarantee: `FOR UPDATE` is a no-op against SQLite, which is all
the data_service unit tests can exercise (CLAUDE.md #14 /
services/data_service/ASSUMPTIONS.md) -- this is the one check the plan
calls out as needing the live database specifically.

Uses a synthetic specialty name and a real patient known (queried live) to
have no diabetes diagnosis, so this test can never collide with a task or an
enrollment the real evaluator would also produce for that patient, and
cleans up everything it created afterward -- including the enrollment row
itself, which `SaveEvaluationResult` creates unconditionally from whatever
the caller asserts (the Data Service does not re-derive eligibility from raw
facts; that's the engine's job) -- so a stray "enrolled in diabetes" row
doesn't linger for other tests or a human to trip over.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import sqlalchemy as sa

from libs.common.grpc_gen import dataservice_pb2 as pb
from tests.integration.support import count_open_tasks_for_key

CONCURRENCY_SPECIALTY = "ConcurrencyTestSpecialty"
CONCURRENCY_PROGRAM = "diabetes_management"
N_CONCURRENT = 20


def _pick_non_diabetic_patient(mysql_engine) -> str:
    with mysql_engine.connect() as conn:
        return conn.execute(
            sa.text(
                """
                SELECT p.patient_id FROM patients p
                WHERE NOT EXISTS (
                    SELECT 1 FROM diagnoses d
                    WHERE d.patient_id = p.patient_id
                      AND (d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%')
                )
                ORDER BY p.patient_id
                LIMIT 1
                """
            )
        ).scalar_one()


def _one_save_call(grpc_stub, patient_id: str, attempt: int) -> pb.SaveEvaluationResultResponse:
    # Distinct idempotency keys per call -- these are meant to model 20
    # independently-triggered evaluations racing each other (e.g. duplicate
    # `patient.changed` messages from different causes), not 20 replays of
    # the exact same one (that scenario is `test_idempotency.py`'s job).
    idempotency_key = hashlib.sha256(
        f"{patient_id}:concurrency-test-{attempt}".encode()
    ).hexdigest()
    need = pb.NeedResult(
        specialty=CONCURRENCY_SPECIALTY,
        cadence_days=30,
        has_upcoming=False,
        decision="scheduling",
    )
    program_result = pb.ProgramResult(
        program_id=CONCURRENCY_PROGRAM,
        program_version=1,
        eligible=True,
        tier="high_risk",
        needs=[need],
    )
    request = pb.SaveEvaluationResultRequest(
        patient_id=patient_id,
        idempotency_key=idempotency_key,
        program_results=[program_result],
        evaluated_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017 -- host venv is py3.10
        next_eval_at="",
    )
    return grpc_stub.SaveEvaluationResult(request, timeout=30)


def test_20_concurrent_saves_create_exactly_one_open_task(grpc_stub, mysql_engine):
    patient_id = _pick_non_diabetic_patient(mysql_engine)
    try:
        with ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
            futures = [
                pool.submit(_one_save_call, grpc_stub, patient_id, i) for i in range(N_CONCURRENT)
            ]
            results = [f.result() for f in as_completed(futures)]

        assert len(results) == N_CONCURRENT

        open_count = count_open_tasks_for_key(
            mysql_engine, patient_id, CONCURRENCY_PROGRAM, CONCURRENCY_SPECIALTY
        )
        assert open_count == 1, (
            f"Expected exactly one open task for {patient_id}/{CONCURRENCY_PROGRAM}/"
            f"{CONCURRENCY_SPECIALTY} after {N_CONCURRENT} concurrent saves, found {open_count}."
        )
    finally:
        with mysql_engine.begin() as conn:
            conn.execute(
                sa.text(
                    "DELETE FROM tasks WHERE patient_id=:p AND program_id=:pr AND specialty=:s"
                ),
                {"p": patient_id, "pr": CONCURRENCY_PROGRAM, "s": CONCURRENCY_SPECIALTY},
            )
            conn.execute(
                sa.text(
                    "DELETE FROM needs WHERE patient_id=:p AND program_id=:pr AND specialty=:s"
                ),
                {"p": patient_id, "pr": CONCURRENCY_PROGRAM, "s": CONCURRENCY_SPECIALTY},
            )
            # This patient had no diabetes_management enrollment before this
            # test (that's why it was picked) -- the enrollment row
            # SaveEvaluationResult created is entirely this test's doing, so
            # it is safe to delete outright rather than restore a prior tier.
            conn.execute(
                sa.text("DELETE FROM enrollments WHERE patient_id=:p AND program_id=:pr"),
                {"p": patient_id, "pr": CONCURRENCY_PROGRAM},
            )
