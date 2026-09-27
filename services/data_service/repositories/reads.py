"""Interactive reads: GetMeta, ListPatients, GetPatient, ListTasks, GetTask,
ListPrograms.

Every filter — including role visibility (`allowed_task_types`) — is applied
in the SQL `WHERE`, never post-filtered in Python: a disallowed filter must
come back as an empty page, never an error (CLAUDE.md #6). The same trick
gives single-row lookups (`GetTask`, and the write RPCs' fetch-for-update) a
free 404 for a task the caller's role may not see, instead of a 403 that
would leak that the task exists.

Pagination: keyset, one stable ascending order per list (`task_id` /
`patient_id`) — see the module docstring in `pagination.py` for why a
general multi-column sort+cursor engine is skipped for the MVP.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from libs.common.dates import days_overdue
from libs.common.errors import NotFoundError
from services.data_service.models import (
    AuditEvent,
    Enrollment,
    Need,
    Patient,
    Program,
    SyncRun,
    Task,
)
from services.data_service.pagination import clamp_limit

DEFAULT_TASK_STATUSES = ("open", "in_progress")


def _age(dob: date, as_of: date) -> int:
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


def patient_to_dict(p: Patient, as_of: date) -> dict[str, Any]:
    return {
        "patient_id": p.patient_id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "date_of_birth": p.date_of_birth.isoformat(),
        "gender": p.gender,
        "phone": p.phone,
        "language": p.language,
        "pcp_provider_name": p.pcp_provider_name,
        "age": _age(p.date_of_birth, as_of),
    }


def enrollment_to_dict(e: Enrollment) -> dict[str, Any]:
    return {
        "program_id": e.program_id,
        "program_version": e.program_version,
        "tier": e.tier,
        "evaluated_at": e.evaluated_at.isoformat(),
    }


def need_to_dict(n: Need) -> dict[str, Any]:
    return {
        "program_id": n.program_id,
        "specialty": n.specialty,
        "cadence_days": n.cadence_days,
        "last_visit_date": n.last_visit_date.isoformat() if n.last_visit_date else None,
        "due_date": n.due_date.isoformat() if n.due_date else None,
        "has_upcoming": n.has_upcoming,
    }


def task_to_dict(t: Task, as_of: date, tier: str | None, patient: dict | None = None) -> dict[str, Any]:
    return {
        "task_id": t.task_id,
        "patient_id": t.patient_id,
        "program_id": t.program_id,
        "tier": tier or "",
        "specialty": t.specialty,
        "task_type": t.task_type,
        "status": t.status,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "days_overdue": days_overdue(t.due_date, as_of),
        "snooze_until": t.snooze_until.isoformat() if t.snooze_until else None,
        "resolution": t.resolution,
        "assigned_to": t.assigned_to,
        "program_version": t.program_version,
        "version": t.version,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "patient": patient,
    }


def tier_map(session: Session, patient_ids: list[str]) -> dict[tuple[str, str], str]:
    """(patient_id, program_id) -> current tier, from `enrollments` — a
    task's tier is not stored on the task row, it always reflects the
    patient's *current* enrollment for that program."""
    if not patient_ids:
        return {}
    rows = session.execute(
        select(Enrollment.patient_id, Enrollment.program_id, Enrollment.tier).where(
            Enrollment.patient_id.in_(patient_ids)
        )
    ).all()
    return {(r.patient_id, r.program_id): r.tier for r in rows}


def _visibility_where(query, allowed_task_types: list[str]):
    """The one place role visibility gets applied: inside the SQL WHERE."""
    return query.where(Task.task_type.in_(allowed_task_types or []))


def get_meta(session: Session, as_of_date: date) -> dict[str, Any]:
    last_sync = session.execute(
        select(func.max(SyncRun.finished_at)).where(SyncRun.status == "completed")
    ).scalar_one_or_none()
    rows = session.execute(select(Task.status, func.count(Task.task_id)).group_by(Task.status)).all()
    return {
        "as_of_date": as_of_date.isoformat(),
        "last_sync_finished_at": last_sync.isoformat() if last_sync else None,
        "task_counts_by_status": {status: count for status, count in rows},
    }


def list_tasks(
    session: Session,
    *,
    allowed_task_types: list[str],
    specialty: str | None,
    task_type: str | None,
    statuses: list[str],
    program: str | None,
    tier: str | None,
    assigned_to: str | None,
    overdue: bool | None,
    include_snoozed: bool,
    limit: int,
    cursor: str | None,
    as_of_date: date,
) -> tuple[list[dict[str, Any]], str | None]:
    limit = clamp_limit(limit)
    q = select(Task)
    q = _visibility_where(q, allowed_task_types)
    if task_type:
        q = q.where(Task.task_type == task_type)
    if specialty:
        q = q.where(Task.specialty == specialty)
    q = q.where(Task.status.in_(statuses or list(DEFAULT_TASK_STATUSES)))
    if program:
        q = q.where(Task.program_id == program)
    if assigned_to:
        q = q.where(Task.assigned_to == assigned_to)
    if overdue:
        q = q.where(Task.due_date.is_not(None)).where(Task.due_date <= as_of_date)
    if not include_snoozed:
        q = q.where(~((Task.snooze_until.is_not(None)) & (Task.snooze_until >= as_of_date)))
    if tier:
        # tier lives on enrollments, joined by (patient_id, program_id)
        q = q.join(
            Enrollment,
            (Enrollment.patient_id == Task.patient_id) & (Enrollment.program_id == Task.program_id),
        ).where(Enrollment.tier == tier)
    if cursor:
        q = q.where(Task.task_id > int(cursor))
    q = q.order_by(Task.task_id.asc()).limit(limit + 1)

    rows = list(session.scalars(q))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = str(rows[-1].task_id)

    patient_ids = [t.patient_id for t in rows]
    tiers = tier_map(session, patient_ids)
    patients = {
        p.patient_id: patient_to_dict(p, as_of_date)
        for p in session.scalars(select(Patient).where(Patient.patient_id.in_(patient_ids)))
    }
    items = [
        task_to_dict(t, as_of_date, tiers.get((t.patient_id, t.program_id)), patients.get(t.patient_id))
        for t in rows
    ]
    return items, next_cursor


def get_task(session: Session, task_id: int, allowed_task_types: list[str], as_of_date: date) -> dict[str, Any]:
    q = _visibility_where(select(Task).where(Task.task_id == task_id), allowed_task_types)
    task = session.scalars(q).one_or_none()
    if task is None:
        raise NotFoundError(f"task {task_id} not found")
    tiers = tier_map(session, [task.patient_id])
    patient = session.get(Patient, task.patient_id)
    task_dict = task_to_dict(
        task, as_of_date, tiers.get((task.patient_id, task.program_id)),
        patient_to_dict(patient, as_of_date) if patient else None,
    )
    history = [
        _audit_to_dict(e)
        for e in session.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity == "task", AuditEvent.patient_id == task.patient_id)
            .order_by(AuditEvent.id.asc())
        )
        if _audit_task_id(e) == task_id
    ]
    return {"task": task_dict, "history": history}


def _audit_task_id(e: AuditEvent) -> int | None:
    # `audit_events` has no `task_id` column (fixed DDL) — every task audit
    # row's before/after JSON carries "task_id", so GetTask's history is
    # resolved by (patient_id, entity='task') then matched here.
    for blob in (e.after_json, e.before_json):
        if blob and "task_id" in blob:
            return blob["task_id"]
    return None


def _audit_to_dict(e: AuditEvent) -> dict[str, Any]:
    return {
        "event_id": e.event_id,
        "occurred_at": e.occurred_at.isoformat(),
        "actor": e.actor,
        "action": e.action,
        "entity": e.entity,
        "patient_id": e.patient_id,
        "before_json": json.dumps(e.before_json) if e.before_json is not None else "",
        "after_json": json.dumps(e.after_json) if e.after_json is not None else "",
        "request_id": e.request_id,
        "result": e.result,
    }


def list_patients(
    session: Session,
    *,
    allowed_task_types: list[str],
    specialty: str | None,
    task_type: str | None,
    status: str | None,
    program: str | None,
    tier: str | None,
    q_text: str | None,
    limit: int,
    cursor: str | None,
    as_of_date: date,
) -> tuple[list[dict[str, Any]], str | None]:
    """`GET /patients?specialty=X` returns patients with a *visible task* for
    that specialty (CLAUDE.md open item, resolved as documented in
    ASSUMPTIONS.md) — so filtering here means "has a matching visible task",
    not "belongs to a program that lists this specialty as a need"."""
    limit = clamp_limit(limit)

    has_task_filter = any([specialty, task_type, status, program, tier])
    pq = select(Patient.patient_id)
    if has_task_filter:
        pq = pq.join(Task, Task.patient_id == Patient.patient_id)
        pq = _visibility_where(pq, allowed_task_types)
        if specialty:
            pq = pq.where(Task.specialty == specialty)
        if task_type:
            pq = pq.where(Task.task_type == task_type)
        if status:
            pq = pq.where(Task.status == status)
        else:
            pq = pq.where(Task.status.in_(DEFAULT_TASK_STATUSES))
        if program:
            pq = pq.where(Task.program_id == program)
        if tier:
            pq = pq.join(
                Enrollment,
                (Enrollment.patient_id == Task.patient_id) & (Enrollment.program_id == Task.program_id),
            ).where(Enrollment.tier == tier)
        pq = pq.distinct()
    if q_text:
        like = f"%{q_text}%"
        pq = pq.where(
            (Patient.first_name.like(like)) | (Patient.last_name.like(like)) | (Patient.patient_id.like(like))
        )
    if cursor:
        pq = pq.where(Patient.patient_id > cursor)
    pq = pq.order_by(Patient.patient_id.asc()).limit(limit + 1)

    patient_ids = [row[0] for row in session.execute(pq).all()]
    next_cursor = None
    if len(patient_ids) > limit:
        patient_ids = patient_ids[:limit]
        next_cursor = patient_ids[-1]

    if not patient_ids:
        return [], None

    patients = {p.patient_id: p for p in session.scalars(select(Patient).where(Patient.patient_id.in_(patient_ids)))}
    enrollments_by_patient: dict[str, list[Enrollment]] = {pid: [] for pid in patient_ids}
    for e in session.scalars(select(Enrollment).where(Enrollment.patient_id.in_(patient_ids))):
        enrollments_by_patient[e.patient_id].append(e)

    tasks_q = _visibility_where(
        select(Task).where(Task.patient_id.in_(patient_ids), Task.status.in_(DEFAULT_TASK_STATUSES)),
        allowed_task_types,
    )
    tasks_by_patient: dict[str, list[Task]] = {pid: [] for pid in patient_ids}
    for t in session.scalars(tasks_q):
        tasks_by_patient[t.patient_id].append(t)
    tiers = tier_map(session, patient_ids)

    items = []
    for pid in patient_ids:
        p = patients[pid]
        items.append(
            {
                "patient": patient_to_dict(p, as_of_date),
                "enrollments": [enrollment_to_dict(e) for e in enrollments_by_patient[pid]],
                "visible_tasks": [
                    task_to_dict(t, as_of_date, tiers.get((t.patient_id, t.program_id)))
                    for t in tasks_by_patient[pid]
                ],
            }
        )
    return items, next_cursor


def get_patient(session: Session, patient_id: str, allowed_task_types: list[str], as_of_date: date) -> dict[str, Any]:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"patient {patient_id} not found")
    enrollments = list(session.scalars(select(Enrollment).where(Enrollment.patient_id == patient_id)))
    needs = list(session.scalars(select(Need).where(Need.patient_id == patient_id)))
    tasks = list(
        session.scalars(
            _visibility_where(
                select(Task).where(Task.patient_id == patient_id, Task.status.in_(DEFAULT_TASK_STATUSES)),
                allowed_task_types,
            )
        )
    )
    tiers = tier_map(session, [patient_id])
    return {
        "patient": patient_to_dict(patient, as_of_date),
        "enrollments": [enrollment_to_dict(e) for e in enrollments],
        "needs": [need_to_dict(n) for n in needs],
        "visible_tasks": [task_to_dict(t, as_of_date, tiers.get((t.patient_id, t.program_id))) for t in tasks],
    }


def list_programs(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(select(Program).where(Program.active.is_(True)))
    return [
        {
            "program_id": p.program_id,
            "version": p.version,
            "definition_json": json.dumps(p.definition),
            "active": p.active,
        }
        for p in rows
    ]


def list_sync_runs(session: Session, limit: int) -> list[dict[str, Any]]:
    limit = clamp_limit(limit, default=20)
    rows = session.scalars(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit))
    return [
        {
            "run_id": r.run_id,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "counts_json": json.dumps(r.counts_json),
            "watermarks_json": json.dumps(r.watermarks_json),
        }
        for r in rows
    ]
