from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.engine.recompute import DEFAULT_AS_OF_DATE
from app.models import AuditLog, Patient, Task, User
from app.routers.common import allowed_task_types, task_matches, task_out, task_row_out
from app.schemas import CompleteBody, DeclineBody, TaskOut, TaskRowOut

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskRowOut])
def list_tasks(
    specialty: str | None = None,
    task_type: str | None = None,
    program: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    allowed = allowed_task_types(user)
    tier_by_program: dict[str, str] = {}  # no tier filter on this endpoint per contract

    patients_by_id = {p.patient_id: p for p in db.query(Patient).all()}
    out: list[TaskRowOut] = []
    for t in db.query(Task).filter(Task.task_type.in_(allowed)).all():
        if not task_matches(t, tier_by_program, specialty=specialty, task_type=task_type, program=program, tier=None, status=status):
            continue
        patient = patients_by_id.get(t.patient_id)
        if patient is None:
            continue
        out.append(task_row_out(t, patient))
    return out


def _load_task_for_action(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.task_type not in allowed_task_types(user):
        raise HTTPException(status_code=403, detail="task type not allowed for this role")
    if task.status != "in_progress" or task.assigned_to != user.name:
        raise HTTPException(status_code=403, detail="not your claim")
    return task


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, body: CompleteBody, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    task = _load_task_for_action(db, task_id, user)
    before = f"status={task.status}"
    task.status = "completed"
    task.resolution = body.resolution
    db.add(AuditLog(
        actor=user.name,
        action="complete",
        patient_id=task.patient_id,
        task_id=task.task_id,
        before=before,
        after=f"status=completed resolution={body.resolution}",
    ))
    db.commit()
    return task_out(task)


@router.post("/tasks/{task_id}/decline", response_model=TaskOut)
def decline_task(task_id: int, body: DeclineBody, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    task = _load_task_for_action(db, task_id, user)
    before = f"status={task.status}"
    task.status = "declined"
    task.reason = body.reason
    task.snooze_until = DEFAULT_AS_OF_DATE + timedelta(days=body.snooze_days)
    db.add(AuditLog(
        actor=user.name,
        action="decline",
        patient_id=task.patient_id,
        task_id=task.task_id,
        before=before,
        after=f"status=declined reason={body.reason} snooze_until={task.snooze_until}",
    ))
    db.commit()
    return task_out(task)
