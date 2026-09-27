"""Stable hashing used for change detection and idempotency.

Plain `hashlib` + `json.dumps(..., sort_keys=True)` — a canonical string,
independent of field/column order, is all "did this row change" or "have we
already applied this evaluation" needs. No hashing library earns its keep
over stdlib here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def row_hash(fields: dict[str, str]) -> str:
    """sha256 hex of a resource row's canonical field values.

    Used for `staging_rows.row_hash` and the live tables' `row_hash` column:
    "changed" means "any mapped field differs", regardless of column order.
    """
    return hashlib.sha256(_canonical(fields).encode("utf-8")).hexdigest()


def snapshot_hash(payload: dict[str, Any]) -> str:
    """sha256 hex of a patient snapshot payload, for the idempotency key."""
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def idempotency_key(patient_id: str, snapshot_hash_value: str) -> str:
    """CLAUDE.md #7: sha256(patient_id + ":" + snapshot_hash)."""
    return hashlib.sha256(f"{patient_id}:{snapshot_hash_value}".encode()).hexdigest()
