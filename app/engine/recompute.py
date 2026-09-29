"""The orchestrator around the pure evaluator: the part that actually does
I/O. Loads every patient's facts + every program, calls `evaluator.
evaluate_patient` per patient (which never touches the DB), diffs the result
against existing tasks, and writes tasks/enrollments/audit rows in one
transaction.

Full-population sweep, every call -- deliberately, at this scale. There is
no per-patient scheduling (`patient_eval_state`/`next_eval_at`) like the
`main` branch has, because nothing here needs to decide "whose turn is it to
be re-checked": with ~300 patients and no live incoming data, re-running
everyone is milliseconds of work. This is exactly the simplification that
stops being true at 1M patients -- see ARCHITECTURE.md.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import evaluator
from app.engine.program_loader import load_programs
from app.models import AuditLog, Diagnosis, Encounter, Enrollment, Lab, Patient, Task

# Matches the CSV data's own era (same default the `main` branch's compose
# file used) -- there's no "today" for a static, one-time dataset.
DEFAULT_AS_OF_DATE = date(2026, 4, 8)

PRIMARY_CARE_SPECIALTIES = frozenset({"PCP"})


def _build_snapshot(session: Session, patient: Patient, as_of_date: date) -> evaluator.PatientSnapshot:
    diagnoses = session.scalars(select(Diagnosis).where(Diagnosis.patient_id == patient.patient_id)).all()
    labs = session.scalars(select(Lab).where(Lab.patient_id == patient.patient_id)).all()
    encounters = session.scalars(select(Encounter).where(Encounter.patient_id == patient.patient_id)).all()
    return evaluator.PatientSnapshot(
        patient_id=patient.patient_id,
        age=evaluator.age_as_of(patient.date_of_birth, as_of_date),
        diagnoses=[evaluator.Diagnosis(d.icd_code, d.diagnosed_date) for d in diagnoses],
        labs=[evaluator.LabResult(lab.test_name, float(lab.result_value), lab.result_date) for lab in labs],
        encounters=[evaluator.Encounter(e.specialty, e.encounter_date) for e in encounters],
    )


def _open_tasks_for_program(session: Session, patient_id: str, program_id: str) -> list[Task]:
    return list(
        session.scalars(
            select(Task).where(
                Task.patient_id == patient_id,
                Task.program_id == program_id,
                Task.status.in_(("open", "in_progress")),
            )
        )
    )


def _find_open_task(session: Session, patient_id: str, program_id: str, specialty: str) -> Task | None:
    return session.scalars(
        select(Task).where(
            Task.patient_id == patient_id,
            Task.program_id == program_id,
            Task.specialty == specialty,
            Task.status.in_(("open", "in_progress")),
        )
    ).one_or_none()


def _latest_task(session: Session, patient_id: str, program_id: str, specialty: str) -> Task | None:
    return session.scalars(
        select(Task)
        .where(Task.patient_id == patient_id, Task.program_id == program_id, Task.specialty == specialty)
        .order_by(Task.task_id.desc())
    ).first()


def _audit(session: Session, *, actor: str, action: str, patient_id: str, task_id: int | None, before: str | None, after: str | None) -> None:
    session.add(AuditLog(actor=actor, action=action, patient_id=patient_id, task_id=task_id, before=before, after=after))


def _close_task(session: Session, task: Task, resolution: str) -> None:
    before = f"status={task.status} due_date={task.due_date}"
    task.status = "closed"
    task.resolution = resolution
    _audit(
        session,
        actor="engine",
        action="task_closed",
        patient_id=task.patient_id,
        task_id=task.task_id,
        before=before,
        after=f"status=closed resolution={resolution}",
    )


def recompute_all(session: Session, programs_dir: str, as_of_date: date = DEFAULT_AS_OF_DATE) -> dict[str, int]:
    programs = load_programs(programs_dir)
    patients = list(session.scalars(select(Patient)))
    created = 0
    closed = 0

    for patient in patients:
        snapshot = _build_snapshot(session, patient, as_of_date)
        for pr in evaluator.evaluate_patient(snapshot, programs, as_of_date, PRIMARY_CARE_SPECIALTIES):
            enrollment = session.get(Enrollment, (patient.patient_id, pr.program_id))

            if not pr.eligible:
                if enrollment is not None:
                    session.delete(enrollment)
                for task in _open_tasks_for_program(session, patient.patient_id, pr.program_id):
                    _close_task(session, task, "not_eligible")
                    closed += 1
                continue

            if enrollment is None:
                session.add(Enrollment(patient_id=patient.patient_id, program_id=pr.program_id, tier=pr.tier))
            else:
                enrollment.tier = pr.tier

            # A specialty that dropped out of the winning tier (tier changed)
            # no longer has a matching need this run -- close its open task.
            evaluated_specialties = {need.specialty for need in pr.needs}
            for task in _open_tasks_for_program(session, patient.patient_id, pr.program_id):
                if task.specialty not in evaluated_specialties:
                    _close_task(session, task, "tier_changed")
                    closed += 1

            for need in pr.needs:
                open_task = _find_open_task(session, patient.patient_id, pr.program_id, need.specialty)

                if need.decision == "no_task":
                    if open_task is not None:
                        resolution = "upcoming_visit" if need.has_upcoming else "visit_found"
                        _close_task(session, open_task, resolution)
                        closed += 1
                    continue

                # decision is "scheduling" or "referral" from here.
                if open_task is not None and open_task.task_type != need.decision:
                    _close_task(session, open_task, "tier_changed")
                    closed += 1
                    open_task = None

                if open_task is not None:
                    continue  # already open with the right type -- leave it, no churn

                latest = _latest_task(session, patient.patient_id, pr.program_id, need.specialty)
                if latest is not None:
                    still_snoozed = latest.status == "declined" and latest.snooze_until is not None and latest.snooze_until >= as_of_date
                    already_handled = latest.status == "completed" and latest.due_date == need.due_date
                    if still_snoozed or already_handled:
                        continue

                new_task = Task(
                    patient_id=patient.patient_id,
                    program_id=pr.program_id,
                    specialty=need.specialty,
                    task_type=need.decision,
                    status="open",
                    due_date=need.due_date,
                )
                session.add(new_task)
                session.flush()  # assigns task_id for the audit row below
                _audit(
                    session,
                    actor="engine",
                    action="task_created",
                    patient_id=patient.patient_id,
                    task_id=new_task.task_id,
                    before=None,
                    after=f"status=open task_type={need.decision} due_date={need.due_date}",
                )
                created += 1

    session.commit()
    return {"patients": len(patients), "created": created, "closed": closed}
