"""Shared bits between patients.py and tasks.py: role-based task_type
filtering (server-side, never trust a client param for this) and the
query-param matching used by both list endpoints."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth import ALLOWED_TASK_TYPES
from app.engine.evaluator import age_as_of
from app.engine.recompute import DEFAULT_AS_OF_DATE
from app.models import Enrollment, Patient, Task, User
from app.schemas import EnrollmentOut, PatientOut, TaskOut, TaskRowOut


def allowed_task_types(user: User) -> set[str]:
    return ALLOWED_TASK_TYPES[user.role]


def task_matches(
    task: Task,
    tier_by_program: dict[str, str],
    *,
    specialty: str | None,
    task_type: str | None,
    program: str | None,
    tier: str | None,
    status: str | None,
) -> bool:
    if specialty is not None and task.specialty != specialty:
        return False
    if task_type is not None and task.task_type != task_type:
        return False
    if program is not None and task.program_id != program:
        return False
    if status is not None and task.status != status:
        return False
    if tier is not None and tier_by_program.get(task.program_id) != tier:
        return False
    return True


def task_out(t: Task) -> TaskOut:
    return TaskOut(
        task_id=t.task_id,
        program_id=t.program_id,
        specialty=t.specialty,
        task_type=t.task_type,
        status=t.status,
        due_date=t.due_date,
        assigned_to=t.assigned_to,
        resolution=t.resolution,
        reason=t.reason,
        snooze_until=t.snooze_until,
    )


def task_row_out(t: Task, patient: Patient) -> TaskRowOut:
    return TaskRowOut(
        task_id=t.task_id,
        patient_id=patient.patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        phone=patient.phone,
        program_id=t.program_id,
        specialty=t.specialty,
        task_type=t.task_type,
        status=t.status,
        due_date=t.due_date,
        assigned_to=t.assigned_to,
        resolution=t.resolution,
        reason=t.reason,
        snooze_until=t.snooze_until,
    )


def build_patient_out(db: Session, patient: Patient, user: User) -> PatientOut:
    """Fresh-from-DB patient shape, role-filtered by task_type only (no
    query-param narrowing) -- used for single-patient results like claim."""
    enrollments = db.query(Enrollment).filter(Enrollment.patient_id == patient.patient_id).all()
    allowed = allowed_task_types(user)
    tasks = db.query(Task).filter(Task.patient_id == patient.patient_id, Task.task_type.in_(allowed)).all()
    return PatientOut(
        patient_id=patient.patient_id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        age=age_as_of(patient.date_of_birth, DEFAULT_AS_OF_DATE),
        phone=patient.phone,
        pcp_provider_name=patient.pcp_provider_name,
        enrollments=[EnrollmentOut(program_id=e.program_id, tier=e.tier) for e in enrollments],
        tasks=[task_out(t) for t in tasks],
    )
