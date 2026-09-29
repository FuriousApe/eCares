"""SQLAlchemy schema for the lean build -- one SQLite file, one process.

Deliberately smaller than the `main` branch's schema: no row_hash/staging
tables (a one-time local CSV read needs no incremental-sync diffing), no
`needs` table (recompute derives needs in memory each run, nothing to
cache), no `programs` table (program YAML is read straight into memory --
nothing else needs to read it back from a DB). Kept: audit_log and the task
lifecycle, because those are genuinely needed regardless of scale.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """2-3 seeded demo accounts. No passwords -- picking a name from a list
    IS the login, per the assessment's own "however you wire up the role
    switch" note. A signed cookie carries user_id after login."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # scheduler | clinical


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(40), nullable=False)
    pcp_provider_name: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    icd_code: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    diagnosed_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (Index("ix_diagnoses_patient", "patient_id"),)


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    test_name: Mapped[str] = mapped_column(String(80), nullable=False)
    result_value: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    result_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (Index("ix_labs_patient", "patient_id"),)


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    specialty: Mapped[str] = mapped_column(String(40), nullable=False)
    encounter_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)

    __table_args__ = (Index("ix_encounters_patient_specialty", "patient_id", "specialty"),)


class Enrollment(Base):
    """Current tier per (patient, program) -- persisted so `GET /patients`
    can show a patient's tier even when they have zero open tasks right
    now. Recomputed wholesale on every recompute run."""

    __tablename__ = "enrollments"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), primary_key=True)
    program_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tier: Mapped[str] = mapped_column(String(40), nullable=False)


TASK_TYPES = ("scheduling", "referral")
TASK_STATUSES = ("open", "in_progress", "completed", "declined", "closed")


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    program_id: Mapped[str] = mapped_column(String(40), nullable=False)
    specialty: Mapped[str] = mapped_column(String(40), nullable=False)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)  # scheduling | referral
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snooze_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Belt-and-suspenders, same trick as `main`: SQLite supports partial
    # unique indexes, so the DB itself refuses a second open/in_progress
    # row for the same (patient, program, specialty) -- not just app logic.
    __table_args__ = (
        Index(
            "uq_one_open_task",
            "patient_id",
            "program_id",
            "specialty",
            unique=True,
            sqlite_where=text("status IN ('open','in_progress')"),
        ),
        Index("ix_tasks_lookup", "patient_id", "program_id", "specialty"),
    )


class AuditLog(Base):
    """Append-only. One row per state change (claim/complete/decline/engine
    close), same transaction as the change itself."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    patient_id: Mapped[str] = mapped_column(String(16), nullable=False)
    task_id: Mapped[int | None] = mapped_column(nullable=True)
    before: Mapped[str | None] = mapped_column(String(500), nullable=True)
    after: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (Index("ix_audit_patient", "patient_id"),)
