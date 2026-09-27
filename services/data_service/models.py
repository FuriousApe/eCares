"""SQLAlchemy models for every table in the plan's MySQL data model.

Only the Data Service imports this module — it is the one component that
holds MySQL credentials. `migrations/env.py` imports `Base.metadata` from
here so Alembic and the ORM never drift apart.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), nullable=False
    )
    icd_code: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    diagnosed_date: Mapped[date] = mapped_column(Date, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "patient_id", "icd_code", "diagnosed_date", name="uq_diagnosis_natural_key"
        ),
        Index("ix_diagnoses_patient", "patient_id"),
    )


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), nullable=False
    )
    test_name: Mapped[str] = mapped_column(String(80), nullable=False)
    result_value: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    result_date: Mapped[date] = mapped_column(Date, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "patient_id", "test_name", "result_date", name="uq_lab_natural_key"
        ),
        Index("ix_labs_patient", "patient_id"),
    )


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), nullable=False
    )
    specialty: Mapped[str] = mapped_column(String(40), nullable=False)
    encounter_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "specialty",
            "encounter_date",
            "provider_name",
            name="uq_encounter_natural_key",
        ),
        Index("ix_encounters_patient_specialty_date", "patient_id", "specialty", "encounter_date"),
    )


class Program(Base):
    __tablename__ = "programs"

    program_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Enrollment(Base):
    __tablename__ = "enrollments"

    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), primary_key=True
    )
    program_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tier: Mapped[str] = mapped_column(String(40), nullable=False)
    program_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Need(Base):
    __tablename__ = "needs"

    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), primary_key=True
    )
    program_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    specialty: Mapped[str] = mapped_column(String(40), primary_key=True)
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False)
    last_visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    has_upcoming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


TASK_TYPES = ("scheduling", "referral")
TASK_STATUSES = ("open", "in_progress", "completed", "declined", "closed")
RESOLUTIONS = (
    "booked",
    "referral_approved",
    "referral_not_indicated",
    "visit_found",
    "upcoming_visit",
    "tier_changed",
    "not_eligible",
)


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), nullable=False
    )
    program_id: Mapped[str] = mapped_column(String(40), nullable=False)
    specialty: Mapped[str] = mapped_column(String(40), nullable=False)
    task_type: Mapped[str] = mapped_column(Enum(*TASK_TYPES), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*TASK_STATUSES), nullable=False, default="open"
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    snooze_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    program_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now()
    )
    open_key: Mapped[str | None] = mapped_column(
        String(80),
        Computed(
            "IF(status IN ('open','in_progress'), "
            "CONCAT(patient_id,'|',program_id,'|',specialty), NULL)",
            persisted=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("open_key", name="uq_one_open_task"),
        Index("ix_worklist", "status", "task_type", "specialty", "due_date"),
        Index("ix_task_patient", "patient_id"),
    )


class PatientEvalState(Base):
    __tablename__ = "patient_eval_state"

    patient_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("patients.patient_id"), primary_key=True
    )
    next_eval_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_eval_state_next_eval_at", "next_eval_at"),)


class Outbox(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    event_key: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_outbox_published_id", "published_at", "id"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str] = mapped_column(String(40), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("ix_audit_patient", "patient_id"),
        Index("ix_audit_entity", "entity"),
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="csv")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    counts_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    watermarks_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SyncQuarantine(Base):
    __tablename__ = "sync_quarantine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_runs.run_id"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_row: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_quarantine_run", "run_id"),)


# --- Staging tables: one per resource, scoped to a single sync run/chunk. ---
# See CLAUDE.md decision #2: keyed by (run_id, resource_type, chunk_number)
# so a retried chunk is delete-then-insert, never an append.


class StagingRow(Base):
    """Generic staging row for all four resources.

    A single table (rather than four near-identical staging tables) because
    the only thing that differs between resources is which keys `fields`
    holds, and the diff step already treats it as an opaque JSON blob to hash
    and compare — a dedicated table per resource would just be four copies of
    the same five columns.
    """

    __tablename__ = "staging_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_number: Mapped[int] = mapped_column(Integer, nullable=False)
    natural_key: Mapped[str] = mapped_column(String(160), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fields: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_staging_run_chunk", "run_id", "resource_type", "chunk_number"),
        Index("ix_staging_natural_key", "resource_type", "natural_key"),
    )
