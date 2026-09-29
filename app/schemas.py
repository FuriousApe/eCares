"""Pydantic response models -- shapes straight from the API contract, no
extra fields, no reuse-driven base classes for shapes that only look
similar."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    name: str
    role: str


class EnrollmentOut(BaseModel):
    program_id: str
    tier: str


class TaskOut(BaseModel):
    task_id: int
    program_id: str
    specialty: str
    task_type: str
    status: str
    due_date: date | None
    assigned_to: str | None
    resolution: str | None
    reason: str | None
    snooze_until: date | None


class PatientOut(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    age: int
    phone: str
    pcp_provider_name: str | None
    enrollments: list[EnrollmentOut]
    tasks: list[TaskOut]


class TaskRowOut(BaseModel):
    task_id: int
    patient_id: str
    patient_name: str
    phone: str
    program_id: str
    specialty: str
    task_type: str
    status: str
    due_date: date | None
    assigned_to: str | None
    resolution: str | None
    reason: str | None
    snooze_until: date | None


class LoginBody(BaseModel):
    user_id: str


class CompleteBody(BaseModel):
    resolution: str


class DeclineBody(BaseModel):
    reason: str
    snooze_days: int
