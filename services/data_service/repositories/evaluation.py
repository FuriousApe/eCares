"""Bulk — engine: GetPatientSnapshot, SaveEvaluationResult, UpsertPrograms,
EnqueueDuePatients, EnqueueAllPatients.

`SaveEvaluationResult` is the one place the plan is genuinely ambiguous
(which resolution a closed task gets) — the picking rule lives in
`evaluation_rules.pick_close_resolution` and is unit-tested there. Locking:
`patient_eval_state` is loaded with `SELECT ... FOR UPDATE` for the whole
diff+write, so concurrent evaluations of the same patient serialize instead
of interleaving into two open tasks for one key.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.common.dates import is_past
from libs.common.errors import NotFoundError
from services.data_service import task_state
from services.data_service.audit import write_audit
from services.data_service.cache import set_active_programs
from services.data_service.db import maybe_for_update
from services.data_service.evaluation_rules import (
    compute_next_eval_at,
    is_snoozed,
    pick_close_resolution,
    snooze_recheck_date,
)
from services.data_service.hashing import snapshot_hash
from services.data_service.models import (
    Diagnosis,
    Encounter,
    Enrollment,
    Lab,
    Need,
    Patient,
    PatientEvalState,
    Program,
    Task,
)
from services.data_service.outbox import write_outbox
from services.data_service.repositories.reads import patient_to_dict

OPEN_STATUSES = ("open", "in_progress")


def get_patient_snapshot(session: Session, patient_id: str, as_of_date: date) -> dict[str, Any]:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"patient {patient_id} not found")

    diagnoses = list(
        session.scalars(
            select(Diagnosis)
            .where(Diagnosis.patient_id == patient_id, Diagnosis.diagnosed_date <= as_of_date)
            .order_by(Diagnosis.diagnosed_date)
        )
    )
    # All HbA1c results, not just the last 6 months — the window length is
    # program-defined data (tier_signal.window_months), not this service's
    # concern; the engine picks the window from what it gets back.
    labs = list(
        session.scalars(
            select(Lab)
            .where(Lab.patient_id == patient_id, Lab.test_name == "HbA1c")
            .order_by(Lab.result_date)
        )
    )
    encounters = list(
        session.scalars(
            select(Encounter).where(Encounter.patient_id == patient_id).order_by(Encounter.encounter_date)
        )
    )

    diagnosis_facts = [
        {"icd_code": d.icd_code, "diagnosed_date": d.diagnosed_date.isoformat()} for d in diagnoses
    ]
    lab_facts = [
        {"test_name": lab.test_name, "result_value": float(lab.result_value), "result_date": lab.result_date.isoformat()}
        for lab in labs
    ]
    encounter_facts = [
        {
            "specialty": e.specialty,
            "encounter_date": e.encounter_date.isoformat(),
            "provider_name": e.provider_name,
            "is_upcoming": not is_past(e.encounter_date, as_of_date),
        }
        for e in encounters
    ]
    patient_fact = patient_to_dict(patient, as_of_date)
    payload = {
        "as_of_date": as_of_date.isoformat(),
        "patient": patient_fact,
        "diagnoses": diagnosis_facts,
        "labs": lab_facts,
        "encounters": encounter_facts,
    }
    return {
        "patient": patient_fact,
        "diagnoses": diagnosis_facts,
        "labs": lab_facts,
        "encounters": encounter_facts,
        "snapshot_hash": snapshot_hash(payload),
    }


def _load_eval_state(session: Session, patient_id: str) -> PatientEvalState:
    q = maybe_for_update(
        select(PatientEvalState).where(PatientEvalState.patient_id == patient_id), session
    )
    state = session.scalars(q).one_or_none()
    if state is None:
        state = PatientEvalState(patient_id=patient_id)
        session.add(state)
        session.flush()
    return state


def _find_open_task(session: Session, patient_id: str, program_id: str, specialty: str) -> Task | None:
    return session.scalars(
        select(Task).where(
            Task.patient_id == patient_id,
            Task.program_id == program_id,
            Task.specialty == specialty,
            Task.status.in_(OPEN_STATUSES),
        )
    ).one_or_none()


def _latest_declined(session: Session, patient_id: str, program_id: str, specialty: str) -> Task | None:
    return session.scalars(
        select(Task)
        .where(
            Task.patient_id == patient_id,
            Task.program_id == program_id,
            Task.specialty == specialty,
            Task.status == "declined",
        )
        .order_by(Task.task_id.desc())
        .limit(1)
    ).one_or_none()


def _close_task(session: Session, task: Task, *, resolution: str, request_id: str) -> None:
    before = {"task_id": task.task_id, "status": task.status, "version": task.version}
    task.status = task_state.next_status(task.status, "close")
    task.resolution = resolution
    task.version += 1
    after = {"task_id": task.task_id, "status": task.status, "version": task.version, "resolution": resolution}
    write_audit(
        session,
        actor="engine",
        action="task_closed",
        entity="task",
        patient_id=task.patient_id,
        before=before,
        after=after,
        request_id=request_id,
    )


# Hysteresis: an open task's due_date only moves if the freshly computed one
# has drifted this far from what's already on the task -- otherwise a
# same-day noise wobble (e.g. a corrected encounter row shifting last_visit
# by a day) would re-target the task every re-evaluation instead of leaving
# it alone.
_DUE_DATE_DEVIATION_DAYS = 60


def _retarget_if_deviated(session: Session, task: Task, new_due_date: date | None, *, request_id: str) -> None:
    if new_due_date is None or task.due_date is None:
        return
    if abs((new_due_date - task.due_date).days) <= _DUE_DATE_DEVIATION_DAYS:
        return
    before = {"task_id": task.task_id, "due_date": task.due_date.isoformat(), "version": task.version}
    task.due_date = new_due_date
    task.version += 1
    write_audit(
        session,
        actor="engine",
        action="task_due_date_updated",
        entity="task",
        patient_id=task.patient_id,
        before=before,
        after={"task_id": task.task_id, "due_date": new_due_date.isoformat(), "version": task.version},
        request_id=request_id,
    )


def save_evaluation_result(
    session: Session,
    *,
    patient_id: str,
    idempotency_key: str,
    program_results: list[dict[str, Any]],
    evaluated_at: datetime,
    next_eval_at_candidate: date | None,
    request_id: str,
    as_of_date: date,
) -> dict[str, Any]:
    """`next_eval_at_candidate` is the engine's own `next_eval_at` — already
    the minimum of every `NeedResult.next_check_candidate` and
    `ProgramResult.tier_recheck_at`, computed with no knowledge of snoozes.
    This function folds in the one thing only the Data Service knows (an
    active decline snooze for a key just evaluated) and takes the overall
    minimum — see `evaluation_rules.compute_next_eval_at`.
    """
    state = _load_eval_state(session, patient_id)
    if state.last_idempotency_key == idempotency_key:
        return {"applied": False, "tasks_created": 0, "tasks_closed": 0}

    tasks_created = 0
    tasks_closed = 0
    next_eval_candidates: list[date | None] = [next_eval_at_candidate]

    for pr in program_results:
        program_id = pr["program_id"]
        previous_enrollment = session.get(Enrollment, (patient_id, program_id))
        previous_tier = previous_enrollment.tier if previous_enrollment else None

        if not pr["eligible"]:
            if previous_enrollment is not None:
                session.delete(previous_enrollment)
            for need_row in session.scalars(
                select(Need).where(Need.patient_id == patient_id, Need.program_id == program_id)
            ):
                session.delete(need_row)
            for open_task in list(
                session.scalars(
                    select(Task).where(
                        Task.patient_id == patient_id,
                        Task.program_id == program_id,
                        Task.status.in_(OPEN_STATUSES),
                    )
                )
            ):
                _close_task(session, open_task, resolution="not_eligible", request_id=request_id)
                tasks_closed += 1
            continue

        tier_changed = previous_tier is not None and previous_tier != pr["tier"]
        if previous_enrollment is None:
            session.add(
                Enrollment(
                    patient_id=patient_id,
                    program_id=program_id,
                    tier=pr["tier"],
                    program_version=pr["program_version"],
                    evaluated_at=evaluated_at,
                )
            )
        else:
            previous_enrollment.tier = pr["tier"]
            previous_enrollment.program_version = pr["program_version"]
            previous_enrollment.evaluated_at = evaluated_at

        evaluated_specialties = {n["specialty"] for n in pr["needs"]}
        stale_needs = list(
            session.scalars(
                select(Need).where(
                    Need.patient_id == patient_id,
                    Need.program_id == program_id,
                    Need.specialty.not_in(evaluated_specialties or {"__none__"}),
                )
            )
        )
        for need_row in stale_needs:
            open_task = _find_open_task(session, patient_id, program_id, need_row.specialty)
            if open_task is not None:
                _close_task(session, open_task, resolution="tier_changed", request_id=request_id)
                tasks_closed += 1
            session.delete(need_row)

        for need in pr["needs"]:
            specialty = need["specialty"]
            need_row = session.get(Need, (patient_id, program_id, specialty))
            if need_row is None:
                need_row = Need(patient_id=patient_id, program_id=program_id, specialty=specialty)
                session.add(need_row)
            need_row.cadence_days = need["cadence_days"]
            need_row.last_visit_date = need["last_visit_date"]
            need_row.due_date = need["due_date"]
            need_row.has_upcoming = need["has_upcoming"]

            open_task = _find_open_task(session, patient_id, program_id, specialty)
            decision = need["decision"]

            if decision == "no_task":
                if open_task is not None:
                    resolution = pick_close_resolution(
                        task_type=open_task.task_type,
                        has_upcoming=need["has_upcoming"],
                        has_past_visit=need["last_visit_date"] is not None,
                        tier_changed=tier_changed,
                        program_eligible=True,
                    )
                    _close_task(session, open_task, resolution=resolution, request_id=request_id)
                    tasks_closed += 1
                continue

            # decision in (scheduling, referral): task_type must equal decision.
            if open_task is not None and open_task.task_type != decision:
                mismatch_resolution = "visit_found" if open_task.task_type == "referral" else "tier_changed"
                _close_task(session, open_task, resolution=mismatch_resolution, request_id=request_id)
                tasks_closed += 1
                open_task = None

            if open_task is not None:
                _retarget_if_deviated(session, open_task, need["due_date"], request_id=request_id)
                continue  # matching open task already exists: no reopen/replace

            declined = _latest_declined(session, patient_id, program_id, specialty)
            if declined is not None and is_snoozed(declined.snooze_until, as_of_date):
                next_eval_candidates.append(snooze_recheck_date(declined.snooze_until))
                continue  # still snoozed: create nothing

            session.add(
                Task(
                    patient_id=patient_id,
                    program_id=program_id,
                    specialty=specialty,
                    task_type=decision,
                    status="open",
                    due_date=need["due_date"],
                    program_version=pr["program_version"],
                )
            )
            tasks_created += 1

    state.last_idempotency_key = idempotency_key
    state.last_evaluated_at = evaluated_at
    state.next_eval_at = compute_next_eval_at(next_eval_candidates)

    write_audit(
        session,
        actor="engine",
        action="evaluation_saved",
        entity="evaluation",
        patient_id=patient_id,
        before=None,
        after={
            "idempotency_key": idempotency_key,
            "tasks_created": tasks_created,
            "tasks_closed": tasks_closed,
        },
        request_id=request_id,
    )
    return {"applied": True, "tasks_created": tasks_created, "tasks_closed": tasks_closed}


def upsert_programs(session: Session, programs: list[dict[str, Any]]) -> int:
    count = 0
    for p in programs:
        existing = session.get(Program, (p["program_id"], p["version"]))
        definition = json.loads(p["definition_json"])
        if existing is None:
            session.add(
                Program(
                    program_id=p["program_id"], version=p["version"], definition=definition, active=p["active"]
                )
            )
        else:
            existing.definition = definition
            existing.active = p["active"]
        count += 1
    session.flush()
    active = list(session.scalars(select(Program).where(Program.active.is_(True))))
    set_active_programs(
        [
            {"program_id": pr.program_id, "version": pr.version, "definition_json": json.dumps(pr.definition), "active": pr.active}
            for pr in active
        ]
    )
    return count


# Commit every N outbox rows so a full-population enqueue doesn't hold one
# multi-million-row transaction (and its row locks) open for its whole run.
_ENQUEUE_COMMIT_CHUNK = 5000


def enqueue_due_patients(session: Session, as_of_date: date) -> int:
    # Sargable range on the indexed column (ix_eval_state_next_eval_at) —
    # wrapping it in func.date(...) would force a full scan instead of using
    # the index, which matters once patient_eval_state has ~1M rows.
    cutoff = datetime.combine(as_of_date, datetime.min.time()) + timedelta(days=1)
    due_ids = list(
        session.scalars(
            select(PatientEvalState.patient_id).where(
                PatientEvalState.next_eval_at.is_not(None),
                PatientEvalState.next_eval_at < cutoff,
            )
        )
    )
    for i, patient_id in enumerate(due_ids, start=1):
        write_outbox(
            session, topic="patient.changed", event_key=patient_id, payload={"patient_id": patient_id, "reason": "due_recheck"}
        )
        if i % _ENQUEUE_COMMIT_CHUNK == 0:
            session.commit()
    return len(due_ids)


def enqueue_all_patients(session: Session) -> int:
    patient_ids = list(session.scalars(select(Patient.patient_id)))
    for i, patient_id in enumerate(patient_ids, start=1):
        write_outbox(
            session, topic="patient.changed", event_key=patient_id, payload={"patient_id": patient_id, "reason": "enqueue_all"}
        )
        if i % _ENQUEUE_COMMIT_CHUNK == 0:
            session.commit()
    return len(patient_ids)
