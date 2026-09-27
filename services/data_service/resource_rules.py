"""Pure validation/parsing rules for the four sync resource types.

No DB access here on purpose — this is what makes `UpsertFacts`'s row-level
validation unit-testable without MySQL (`tests/test_resource_rules.py`).
Canonical field names per CLAUDE.md #1; the mapper (sync's job) already
produces exactly these keys, so this module only has to validate shape and
parse types.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

RESOURCE_TYPES = ("patients", "diagnoses", "labs", "encounters")

_REQUIRED: dict[str, tuple[str, ...]] = {
    "patients": (
        "patient_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "gender",
        "phone",
        "language",
    ),
    "diagnoses": ("patient_id", "icd_code", "description", "diagnosed_date"),
    "labs": ("patient_id", "test_name", "result_value", "result_date"),
    "encounters": ("patient_id", "specialty", "encounter_date", "provider_name"),
}

_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "patients": ("date_of_birth",),
    "diagnoses": ("diagnosed_date",),
    "labs": ("result_date",),
    "encounters": ("encounter_date",),
}

# Model field names for the three child resources — the parsed dict's keys
# line up 1:1 with the SQLAlchemy model's columns, so callers can just do
# `model(**{f: parsed[f] for f in MODEL_FIELDS[resource_type]})`.
MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "diagnoses": ("patient_id", "icd_code", "description", "diagnosed_date"),
    "labs": ("patient_id", "test_name", "result_value", "result_date"),
    "encounters": ("patient_id", "specialty", "encounter_date", "provider_name"),
}

FK_PATIENT_RESOURCES = ("diagnoses", "labs", "encounters")


class RowRejected(ValueError):
    """Raised by `parse_row` with a human-readable reason for the reject."""


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%Y-%m-%d").date()


def parse_row(resource_type: str, fields: dict[str, str]) -> dict[str, Any]:
    """Validates shape + coerces types. Raises `RowRejected` on any problem."""
    if resource_type not in RESOURCE_TYPES:
        raise RowRejected(f"unknown resource_type {resource_type!r}")

    missing = [f for f in _REQUIRED[resource_type] if not (fields.get(f) or "").strip()]
    if missing:
        raise RowRejected(f"missing required field(s): {', '.join(missing)}")

    parsed: dict[str, Any] = dict(fields)
    for date_field in _DATE_FIELDS[resource_type]:
        try:
            parsed[date_field] = _parse_date(fields[date_field])
        except ValueError as exc:
            raise RowRejected(
                f"{date_field} is not a valid ISO date: {fields[date_field]!r}"
            ) from exc

    if resource_type == "labs":
        try:
            parsed["result_value"] = float(fields["result_value"])
        except ValueError as exc:
            raise RowRejected(f"result_value is not numeric: {fields['result_value']!r}") from exc

    if resource_type == "patients":
        parsed["pcp_provider_name"] = (fields.get("pcp_provider_name") or "").strip() or None

    return parsed


def natural_key(resource_type: str, parsed: dict[str, Any]) -> str:
    if resource_type == "patients":
        parts = [parsed["patient_id"]]
    elif resource_type == "diagnoses":
        parts = [parsed["patient_id"], parsed["icd_code"], parsed["diagnosed_date"].isoformat()]
    elif resource_type == "labs":
        parts = [parsed["patient_id"], parsed["test_name"], parsed["result_date"].isoformat()]
    elif resource_type == "encounters":
        parts = [
            parsed["patient_id"],
            parsed["specialty"],
            parsed["encounter_date"].isoformat(),
            parsed["provider_name"],
        ]
    else:
        raise RowRejected(f"unknown resource_type {resource_type!r}")
    return "|".join(parts)
