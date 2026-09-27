"""Pydantic v2 request/response models for the Worklist API.

These mirror the proto messages in `proto/dataservice.proto` field-for-field
(see `mapping.py` for the conversion) plus the request bodies for the four
task mutations, which Pydantic validates before any gRPC call is made.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class PatientOut(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    phone: str
    language: str
    pcp_provider_name: str | None = None
    age: int


class EnrollmentOut(BaseModel):
    program_id: str
    program_version: int
    tier: str
    evaluated_at: str


class NeedOut(BaseModel):
    program_id: str
    specialty: str
    cadence_days: int
    last_visit_date: str | None = None
    due_date: str | None = None
    has_upcoming: bool


class TaskOut(BaseModel):
    task_id: int
    patient_id: str
    program_id: str
    tier: str
    specialty: str
    task_type: str
    status: str
    due_date: str | None = None
    days_overdue: int | None = None
    snooze_until: str | None = None
    resolution: str | None = None
    assigned_to: str | None = None
    program_version: int
    version: int
    created_at: str
    updated_at: str
    patient: PatientOut | None = None


class PatientWithContextOut(BaseModel):
    patient: PatientOut
    enrollments: list[EnrollmentOut]
    visible_tasks: list[TaskOut]


class ListPatientsResponseOut(BaseModel):
    items: list[PatientWithContextOut]
    next_cursor: str | None = None


class PatientDetailOut(BaseModel):
    patient: PatientOut
    enrollments: list[EnrollmentOut]
    needs: list[NeedOut]
    visible_tasks: list[TaskOut]


class ListTasksResponseOut(BaseModel):
    items: list[TaskOut]
    next_cursor: str | None = None


class AuditEntryOut(BaseModel):
    event_id: str
    occurred_at: str
    actor: str
    action: str
    entity: str
    patient_id: str | None = None
    before_json: str
    after_json: str
    request_id: str
    result: str


class TaskDetailOut(BaseModel):
    task: TaskOut
    history: list[AuditEntryOut]


class ProgramOut(BaseModel):
    program_id: str
    version: int
    definition_json: str
    active: bool


class ListProgramsResponseOut(BaseModel):
    items: list[ProgramOut]


class MetaOut(BaseModel):
    as_of_date: str
    last_sync_finished_at: str | None = None
    task_counts_by_status: dict[str, int]


class HealthOut(BaseModel):
    status: str = "ok"


class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str


# --- task mutation bodies ---


class ClaimTaskBody(BaseModel):
    version: int


class CompleteTaskBody(BaseModel):
    version: int
    resolution: Literal["booked", "referral_approved", "referral_not_indicated"]
    note: str | None = None


class DeclineTaskBody(BaseModel):
    version: int
    reason: str
    snooze_days: int = 90


class SnoozeTaskBody(BaseModel):
    version: int
    until: date
    reason: str


# --- admin ---


class SyncRunOut(BaseModel):
    run_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    counts_json: str
    watermarks_json: str


class SyncTriggerOut(BaseModel):
    run: SyncRunOut
    changed_patient_ids: list[str]


class ListSyncRunsOut(BaseModel):
    items: list[SyncRunOut]


class EvaluateTriggerOut(BaseModel):
    enqueued_count: int
    scope: Literal["patient", "all"]
    note: str | None = None
