"""Proto <-> Pydantic conversions, and the one place a `RoleFilter` is built."""

from __future__ import annotations

from datetime import date

from libs.common import dates
from libs.common.grpc_gen import dataservice_pb2 as pb
from services.worklist_api.deps import Caller
from services.worklist_api.schemas import (
    AuditEntryOut,
    EnrollmentOut,
    NeedOut,
    PatientOut,
    ProgramOut,
    SyncRunOut,
    TaskOut,
)


def role_filter(caller: Caller) -> pb.RoleFilter:
    # Role visibility ALWAYS comes from the caller's resolved role, never
    # from a client-supplied value.
    return pb.RoleFilter(
        allowed_task_types=list(caller.allowed_task_types),
        role=caller.role,
        user_id=caller.user_id,
    )


def patient_out(p: pb.Patient) -> PatientOut:
    return PatientOut(
        patient_id=p.patient_id,
        first_name=p.first_name,
        last_name=p.last_name,
        date_of_birth=p.date_of_birth,
        gender=p.gender,
        phone=p.phone,
        language=p.language,
        pcp_provider_name=p.pcp_provider_name if p.HasField("pcp_provider_name") else None,
        age=p.age,
    )


def enrollment_out(e: pb.Enrollment) -> EnrollmentOut:
    return EnrollmentOut(
        program_id=e.program_id,
        program_version=e.program_version,
        tier=e.tier,
        evaluated_at=e.evaluated_at,
    )


def need_out(n: pb.Need) -> NeedOut:
    return NeedOut(
        program_id=n.program_id,
        specialty=n.specialty,
        cadence_days=n.cadence_days,
        last_visit_date=n.last_visit_date if n.HasField("last_visit_date") else None,
        due_date=n.due_date if n.HasField("due_date") else None,
        has_upcoming=n.has_upcoming,
    )


def task_out(t: pb.Task, as_of_date: date) -> TaskOut:
    due_date = t.due_date if t.HasField("due_date") else None
    # Days overdue is not stored (per the plan) — use the Data Service's
    # value when it sent one, else compute it here from due_date.
    if t.HasField("days_overdue"):
        overdue = t.days_overdue
    elif due_date:
        overdue = dates.days_overdue(date.fromisoformat(due_date), as_of_date)
    else:
        overdue = None
    return TaskOut(
        task_id=t.task_id,
        patient_id=t.patient_id,
        program_id=t.program_id,
        tier=t.tier,
        specialty=t.specialty,
        task_type=t.task_type,
        status=t.status,
        due_date=due_date,
        days_overdue=overdue,
        snooze_until=t.snooze_until if t.HasField("snooze_until") else None,
        resolution=t.resolution if t.HasField("resolution") else None,
        assigned_to=t.assigned_to if t.HasField("assigned_to") else None,
        program_version=t.program_version,
        version=t.version,
        created_at=t.created_at,
        updated_at=t.updated_at,
        patient=patient_out(t.patient) if t.HasField("patient") else None,
    )


def audit_entry_out(a: pb.AuditEntry) -> AuditEntryOut:
    return AuditEntryOut(
        event_id=a.event_id,
        occurred_at=a.occurred_at,
        actor=a.actor,
        action=a.action,
        entity=a.entity,
        patient_id=a.patient_id if a.HasField("patient_id") else None,
        before_json=a.before_json,
        after_json=a.after_json,
        request_id=a.request_id,
        result=a.result,
    )


def program_out(p: pb.Program) -> ProgramOut:
    return ProgramOut(
        program_id=p.program_id,
        version=p.version,
        definition_json=p.definition_json,
        active=p.active,
    )


def sync_run_out(r: pb.SyncRun) -> SyncRunOut:
    return SyncRunOut(
        run_id=r.run_id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at if r.HasField("finished_at") else None,
        counts_json=r.counts_json,
        watermarks_json=r.watermarks_json,
    )
