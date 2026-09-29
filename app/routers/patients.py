from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.engine.evaluator import age_as_of
from app.engine.recompute import DEFAULT_AS_OF_DATE
from app.models import AuditLog, Enrollment, Patient, Task, User
from app.routers.common import allowed_task_types, build_patient_out, task_matches, task_out
from app.schemas import EnrollmentOut, PatientOut

router = APIRouter(tags=["patients"])


@router.get("/patients", response_model=list[PatientOut])
def list_patients(
    specialty: str | None = None,
    task_type: str | None = None,
    program: str | None = None,
    tier: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    allowed = allowed_task_types(user)
    any_filter = any(v is not None for v in (specialty, task_type, program, tier, status))

    out: list[PatientOut] = []
    for patient in db.query(Patient).order_by(Patient.patient_id).all():
        enrollments = db.query(Enrollment).filter(Enrollment.patient_id == patient.patient_id).all()
        tier_by_program = {e.program_id: e.tier for e in enrollments}
        role_tasks = db.query(Task).filter(Task.patient_id == patient.patient_id, Task.task_type.in_(allowed)).all()

        if any_filter:
            tasks = [t for t in role_tasks if task_matches(t, tier_by_program, specialty=specialty, task_type=task_type, program=program, tier=tier, status=status)]
            if not tasks:
                continue
        else:
            tasks = role_tasks

        out.append(PatientOut(
            patient_id=patient.patient_id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            age=age_as_of(patient.date_of_birth, DEFAULT_AS_OF_DATE),
            phone=patient.phone,
            pcp_provider_name=patient.pcp_provider_name,
            enrollments=[EnrollmentOut(program_id=e.program_id, tier=e.tier) for e in enrollments],
            tasks=[task_out(t) for t in tasks],
        ))
    return out


@router.post("/patients/{patient_id}/claim", response_model=PatientOut)
def claim_patient(patient_id: str, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="patient not found")

    allowed = allowed_task_types(user)
    tasks = db.query(Task).filter(Task.patient_id == patient_id, Task.status == "open", Task.task_type.in_(allowed)).all()
    if not tasks:
        raise HTTPException(status_code=409, detail="no open tasks to claim for this patient")

    claimed_ids = []
    for t in tasks:
        t.status = "in_progress"
        t.assigned_to = user.name
        claimed_ids.append(t.task_id)

    db.add(AuditLog(
        actor=user.name,
        action="claim",
        patient_id=patient_id,
        task_id=None,
        before="status=open",
        after=f"status=in_progress assigned_to={user.name} task_ids={claimed_ids}",
    ))
    db.commit()
    return build_patient_out(db, patient, user)
