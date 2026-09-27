"""Bulk — sync: StartSyncRun, UpsertFacts, CompleteSyncRun, ListSyncRuns.

Per CLAUDE.md #1-3: `UpsertFacts` deep-validates and hashes each row, staging
it (delete-then-insert per `(run_id, resource_type, chunk_number)` so a
retried chunk is a no-op) or writing straight to `sync_quarantine` when it
doesn't parse. `CompleteSyncRun` diffs staging against the live tables by
natural key and enforces the patients FK that `UpsertFacts` deliberately
deferred.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from libs.common.errors import NotFoundError, ValidationError
from services.data_service import resource_rules
from services.data_service.hashing import row_hash
from services.data_service.models import (
    Diagnosis,
    Encounter,
    Lab,
    Patient,
    StagingRow,
    SyncQuarantine,
    SyncRun,
)
from services.data_service.outbox import write_outbox

_CHILD_MODELS = {"diagnoses": Diagnosis, "labs": Lab, "encounters": Encounter}


def start_sync_run(session: Session, source: str) -> str:
    run_id = uuid.uuid4().hex
    session.add(SyncRun(run_id=run_id, source=source or "csv", status="running"))
    return run_id


def upsert_facts(
    session: Session,
    *,
    run_id: str,
    resource_type: str,
    chunk_number: int,
    rows: list[dict[str, str]],
) -> tuple[int, list[dict[str, Any]]]:
    if session.get(SyncRun, run_id) is None:
        raise NotFoundError(f"sync run {run_id} not found")
    if resource_type not in resource_rules.RESOURCE_TYPES:
        raise ValidationError(f"unknown resource_type {resource_type!r}")

    accepted: list[tuple[str, str, dict[str, str]]] = []
    rejected: list[dict[str, Any]] = []
    for raw in rows:
        try:
            parsed = resource_rules.parse_row(resource_type, raw)
        except resource_rules.RowRejected as exc:
            rejected.append({"raw": raw, "reason": str(exc)})
            session.add(
                SyncQuarantine(run_id=run_id, resource_type=resource_type, raw_row=raw, reason=str(exc))
            )
            continue
        natural_key = resource_rules.natural_key(resource_type, parsed)
        accepted.append((natural_key, row_hash(raw), raw))

    # Idempotent retry: this chunk's prior staging rows (if any) are replaced
    # wholesale, never appended to.
    session.execute(
        delete(StagingRow).where(
            StagingRow.run_id == run_id,
            StagingRow.resource_type == resource_type,
            StagingRow.chunk_number == chunk_number,
        )
    )
    for natural_key, hash_value, raw in accepted:
        session.add(
            StagingRow(
                run_id=run_id,
                resource_type=resource_type,
                chunk_number=chunk_number,
                natural_key=natural_key,
                row_hash=hash_value,
                fields=raw,
            )
        )
    return len(accepted), rejected


def _dedup_by_natural_key(rows: list[StagingRow]) -> dict[str, StagingRow]:
    """A duplicate natural key within the same sync (e.g. the plan's P0231
    2024-10-02 duplicate encounter) must collapse to exactly one row. We keep
    the first one written (lowest staging row id — earliest chunk/call)."""
    result: dict[str, StagingRow] = {}
    for r in sorted(rows, key=lambda r: r.id):
        result.setdefault(r.natural_key, r)
    return result


def _staged_rows(session: Session, run_id: str, resource_type: str) -> dict[str, StagingRow]:
    rows = list(
        session.scalars(
            select(StagingRow).where(
                StagingRow.run_id == run_id, StagingRow.resource_type == resource_type
            )
        )
    )
    return _dedup_by_natural_key(rows)


def _promote_patients(session: Session, run_id: str) -> tuple[set[str], int, int]:
    """Returns (changed_patient_ids, accepted_count, rejected_count)."""
    staged = _staged_rows(session, run_id, "patients")
    changed: set[str] = set()
    for row in staged.values():
        parsed = resource_rules.parse_row("patients", row.fields)
        pid = parsed["patient_id"]
        existing = session.get(Patient, pid)
        if existing is None:
            session.add(
                Patient(
                    patient_id=pid,
                    first_name=parsed["first_name"],
                    last_name=parsed["last_name"],
                    date_of_birth=parsed["date_of_birth"],
                    gender=parsed["gender"],
                    phone=parsed["phone"],
                    language=parsed["language"],
                    pcp_provider_name=parsed["pcp_provider_name"],
                    row_hash=row.row_hash,
                )
            )
            changed.add(pid)
        elif existing.row_hash != row.row_hash:
            existing.first_name = parsed["first_name"]
            existing.last_name = parsed["last_name"]
            existing.date_of_birth = parsed["date_of_birth"]
            existing.gender = parsed["gender"]
            existing.phone = parsed["phone"]
            existing.language = parsed["language"]
            existing.pcp_provider_name = parsed["pcp_provider_name"]
            existing.row_hash = row.row_hash
            changed.add(pid)
    session.flush()  # child resources' FK check must see these patients
    rejected_count = session.query(SyncQuarantine).filter_by(run_id=run_id, resource_type="patients").count()
    return changed, len(staged), rejected_count


def _promote_child_resource(session: Session, run_id: str, resource_type: str) -> tuple[set[str], int, int]:
    staged = _staged_rows(session, run_id, resource_type)
    model = _CHILD_MODELS[resource_type]
    fields = resource_rules.MODEL_FIELDS[resource_type]
    live_patient_ids = {pid for (pid,) in session.execute(select(Patient.patient_id)).all()}

    changed: set[str] = set()
    accepted = 0
    for row in staged.values():
        parsed = resource_rules.parse_row(resource_type, row.fields)
        pid = parsed["patient_id"]
        if pid not in live_patient_ids:
            session.add(
                SyncQuarantine(
                    run_id=run_id,
                    resource_type=resource_type,
                    raw_row=row.fields,
                    reason=f"patient_id {pid!r} not found (deferred FK check)",
                )
            )
            continue
        existing = session.scalars(
            select(model).filter_by(**{f: parsed[f] for f in fields})
        ).one_or_none()
        if existing is None:
            session.add(model(row_hash=row.row_hash, **{f: parsed[f] for f in fields}))
            changed.add(pid)
        elif existing.row_hash != row.row_hash:
            for f in fields:
                setattr(existing, f, parsed[f])
            existing.row_hash = row.row_hash
            changed.add(pid)
        accepted += 1

    rejected_count = (
        session.query(SyncQuarantine).filter_by(run_id=run_id, resource_type=resource_type).count()
    )
    return changed, accepted, rejected_count


def complete_sync_run(session: Session, *, run_id: str, status: str) -> dict[str, Any]:
    run = session.get(SyncRun, run_id)
    if run is None:
        raise NotFoundError(f"sync run {run_id} not found")

    counts: dict[str, dict[str, int]] = {}
    changed_patient_ids: set[str] = set()

    patients_changed, patients_accepted, patients_rejected = _promote_patients(session, run_id)
    changed_patient_ids |= patients_changed
    counts["patients"] = {"accepted": patients_accepted, "rejected": patients_rejected}

    for resource_type in ("diagnoses", "labs", "encounters"):
        rt_changed, rt_accepted, rt_rejected = _promote_child_resource(session, run_id, resource_type)
        changed_patient_ids |= rt_changed
        counts[resource_type] = {"accepted": rt_accepted, "rejected": rt_rejected}

    for patient_id in sorted(changed_patient_ids):
        write_outbox(
            session,
            topic="patient.changed",
            event_key=patient_id,
            payload={"patient_id": patient_id, "reason": "sync"},
        )

    run.status = status
    run.finished_at = datetime.utcnow()
    run.counts_json = counts
    session.flush()
    return {
        "run_id": run.run_id,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat(),
        "counts_json": json.dumps(counts),
        "watermarks_json": json.dumps(run.watermarks_json),
        "changed_patient_ids": sorted(changed_patient_ids),
    }
