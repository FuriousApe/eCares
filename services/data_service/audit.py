"""Writing `audit_events` rows.

Every state-changing RPC writes one row in the same transaction as the
change it audits (see `db.session_scope`). Reads write a lightweight row too
(`GetPatient` per-call, `ListTasks`/`ListPatients` one row per call recording
filters + row count, not per returned row).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from services.data_service.models import AuditEvent


def write_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    entity: str,
    patient_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    request_id: str,
    result: str = "success",
) -> AuditEvent:
    event = AuditEvent(
        event_id=uuid.uuid4().hex,
        actor=actor or "unknown",
        action=action,
        entity=entity,
        patient_id=patient_id,
        before_json=before,
        after_json=after,
        request_id=request_id or "",
        result=result,
    )
    session.add(event)
    return event
