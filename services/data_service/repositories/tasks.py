"""Interactive write: ClaimTask, CompleteTask, DeclineTask, SnoozeTask.

Every transition: lock the row, check the version, validate the transition
(`task_state.next_status`), write the change + an audit row + an outbox row
in the caller's transaction. The cache generation bump happens after the
transaction commits (see `servicer.py`) — Redis isn't part of the MySQL
transaction, so there is no point bumping it before we know the commit held.

Row locking: `SELECT ... FOR UPDATE` on MySQL so two concurrent mutations of
the same task serialize instead of racing on a stale read; skipped on SQLite
(unsupported) since the unit tests here are single-threaded anyway.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.common.errors import NotFoundError, VersionConflictError
from services.data_service import task_state
from services.data_service.audit import write_audit
from services.data_service.db import maybe_for_update
from services.data_service.models import Task
from services.data_service.outbox import write_outbox
from services.data_service.repositories.reads import tier_map, task_to_dict


def _load_task(session: Session, task_id: int, allowed_task_types: list[str]) -> Task:
    q = maybe_for_update(
        select(Task).where(Task.task_id == task_id, Task.task_type.in_(allowed_task_types or [])),
        session,
    )
    task = session.scalars(q).one_or_none()
    if task is None:
        raise NotFoundError(f"task {task_id} not found")
    return task


def _check_version(task: Task, expected_version: int) -> None:
    if task.version != expected_version:
        raise VersionConflictError(
            f"task {task.task_id} is at version {task.version}, expected {expected_version}"
        )


def _snapshot(task: Task) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "status": task.status,
        "version": task.version,
        "assigned_to": task.assigned_to,
        "resolution": task.resolution,
        "snooze_until": task.snooze_until.isoformat() if task.snooze_until else None,
    }


def _apply_transition(
    session: Session,
    *,
    task: Task,
    action: str,
    actor: str,
    role: str,
    request_id: str,
    audit_action: str,
    extra_after: dict[str, Any] | None = None,
    mutate,
) -> None:
    before = _snapshot(task)
    task.status = task_state.next_status(task.status, action)
    mutate(task)
    task.version += 1
    after = _snapshot(task)
    if extra_after:
        after.update(extra_after)
    write_audit(
        session,
        actor=actor or role,
        action=audit_action,
        entity="task",
        patient_id=task.patient_id,
        before=before,
        after=after,
        request_id=request_id,
    )
    write_outbox(
        session,
        topic="patient.changed",
        event_key=task.patient_id,
        payload={"patient_id": task.patient_id, "reason": audit_action, "task_id": task.task_id},
    )


def _result(session: Session, task: Task, as_of_date: date) -> dict[str, Any]:
    tier = tier_map(session, [task.patient_id]).get((task.patient_id, task.program_id))
    return task_to_dict(task, as_of_date, tier)


def claim_task(
    session: Session, *, task_id: int, version: int, role_filter, request_id: str, as_of_date: date
) -> dict[str, Any]:
    task = _load_task(session, task_id, list(role_filter.allowed_task_types))
    _check_version(task, version)

    def mutate(t: Task) -> None:
        t.assigned_to = role_filter.user_id

    _apply_transition(
        session,
        task=task,
        action="claim",
        actor=role_filter.user_id,
        role=role_filter.role,
        request_id=request_id,
        audit_action="task_claimed",
        mutate=mutate,
    )
    return _result(session, task, as_of_date)


def complete_task(
    session: Session,
    *,
    task_id: int,
    version: int,
    resolution: str,
    note: str | None,
    role_filter,
    request_id: str,
    as_of_date: date,
) -> dict[str, Any]:
    task = _load_task(session, task_id, list(role_filter.allowed_task_types))
    _check_version(task, version)

    def mutate(t: Task) -> None:
        t.resolution = resolution

    _apply_transition(
        session,
        task=task,
        action="complete",
        actor=role_filter.user_id,
        role=role_filter.role,
        request_id=request_id,
        audit_action="task_completed",
        extra_after={"note": note} if note else None,
        mutate=mutate,
    )
    return _result(session, task, as_of_date)


def decline_task(
    session: Session,
    *,
    task_id: int,
    version: int,
    reason: str,
    snooze_days: int,
    role_filter,
    request_id: str,
    as_of_date: date,
    default_snooze_days: int,
) -> dict[str, Any]:
    task = _load_task(session, task_id, list(role_filter.allowed_task_types))
    _check_version(task, version)
    days = snooze_days if snooze_days and snooze_days > 0 else default_snooze_days

    def mutate(t: Task) -> None:
        t.snooze_until = as_of_date + timedelta(days=days)

    _apply_transition(
        session,
        task=task,
        action="decline",
        actor=role_filter.user_id,
        role=role_filter.role,
        request_id=request_id,
        audit_action="task_declined",
        extra_after={"reason": reason, "snooze_days": days},
        mutate=mutate,
    )
    return _result(session, task, as_of_date)


def snooze_task(
    session: Session,
    *,
    task_id: int,
    version: int,
    until: date,
    reason: str,
    role_filter,
    request_id: str,
    as_of_date: date,
) -> dict[str, Any]:
    task = _load_task(session, task_id, list(role_filter.allowed_task_types))
    _check_version(task, version)

    def mutate(t: Task) -> None:
        t.snooze_until = until
        t.assigned_to = None  # back in the shared pool until the snooze passes

    _apply_transition(
        session,
        task=task,
        action="snooze",
        actor=role_filter.user_id,
        role=role_filter.role,
        request_id=request_id,
        audit_action="task_snoozed",
        extra_after={"reason": reason},
        mutate=mutate,
    )
    return _result(session, task, as_of_date)
