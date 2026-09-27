"""CSV column name -> canonical field name mappers, one function per resource.

The four source CSVs already use the canonical field names as headers
(CLAUDE.md decision #1), so each function below is close to a pass-through.
It stays an explicit function per resource anyway -- not a bare `dict(row)`
cast -- so a future non-CSV adapter (FHIR, deferred) has one clear seam per
resource to satisfy instead of matching a CSV header layout.

Validation split (see CLAUDE.md decision #1 and the plan's rule
interpretations):

- Sync's job is a *light shape check*: does this raw row even parse into
  something worth sending at all? Required columns present, non-blank
  `patient_id`, a plausible `YYYY-MM-DD` date where a date is expected.
- Everything else -- an unknown `patient_id` (FK), a bad ICD code, a lab
  value that doesn't parse as a number, a duplicate natural key -- is a Data
  Service concern (it owns hashing, persistence and `sync_quarantine`, since
  only it holds MySQL credentials).
- A *blank* `pcp_provider_name` is NOT a shape problem. The plan is explicit
  that "a missing PCP name is not 'no PCP history'" -- that's a Data Service
  semantic call (PCP history comes from encounters instead), so sync passes
  a blank name through faithfully as `""` rather than rejecting the row.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MalformedRowError(ValueError):
    """Raised when a raw row is too broken to send on at all."""


def _require_keys(resource_type: str, row: dict[str, str], keys: tuple[str, ...]) -> None:
    missing = [k for k in keys if k not in row]
    if missing:
        raise MalformedRowError(f"{resource_type} row missing column(s) {missing}: {row}")


def map_patient(row: dict[str, str]) -> dict[str, str]:
    _require_keys(
        "patients",
        row,
        ("patient_id", "first_name", "last_name", "date_of_birth", "gender", "phone", "language"),
    )
    return {
        "patient_id": row["patient_id"].strip(),
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "date_of_birth": row["date_of_birth"],
        "gender": row["gender"],
        "phone": row["phone"],
        "language": row["language"],
        # Nullable in the DB; blank is faithful, not an error (see module docstring).
        "pcp_provider_name": row.get("pcp_provider_name") or "",
    }


def map_diagnosis(row: dict[str, str]) -> dict[str, str]:
    _require_keys("diagnoses", row, ("patient_id", "icd_code", "description", "diagnosed_date"))
    return {
        "patient_id": row["patient_id"].strip(),
        "icd_code": row["icd_code"],
        "description": row["description"],
        "diagnosed_date": row["diagnosed_date"],
    }


def map_lab(row: dict[str, str]) -> dict[str, str]:
    _require_keys("labs", row, ("patient_id", "test_name", "result_value", "result_date"))
    return {
        "patient_id": row["patient_id"].strip(),
        "test_name": row["test_name"],
        "result_value": row["result_value"],
        "result_date": row["result_date"],
    }


def map_encounter(row: dict[str, str]) -> dict[str, str]:
    _require_keys(
        "encounters", row, ("patient_id", "specialty", "encounter_date", "provider_name")
    )
    return {
        "patient_id": row["patient_id"].strip(),
        "specialty": row["specialty"],
        "encounter_date": row["encounter_date"],
        "provider_name": row["provider_name"],
    }


MAPPERS: dict[str, Callable[[dict[str, str]], dict[str, str]]] = {
    "patients": map_patient,
    "diagnoses": map_diagnosis,
    "labs": map_lab,
    "encounters": map_encounter,
}

# Which mapped field holds the resource's date, for the shape check below.
_DATE_FIELD = {
    "patients": "date_of_birth",
    "diagnoses": "diagnosed_date",
    "labs": "result_date",
    "encounters": "encounter_date",
}


def validate_shape(resource_type: str, mapped: dict[str, str]) -> None:
    """Raises `MalformedRowError` if the mapped row is too broken to send.

    Deliberately shallow: non-blank `patient_id`, and a plausible
    `YYYY-MM-DD` date. Whether that patient_id or date is actually valid is
    the Data Service's job (see module docstring).
    """
    if not mapped.get("patient_id", "").strip():
        raise MalformedRowError(f"{resource_type} row has a blank patient_id: {mapped}")
    date_field = _DATE_FIELD[resource_type]
    date_value = mapped.get(date_field) or ""
    if not _DATE_RE.match(date_value):
        raise MalformedRowError(
            f"{resource_type} row has a malformed {date_field}: {date_value!r}"
        )


def map_and_validate(resource_type: str, raw_row: dict[str, str]) -> dict[str, str]:
    """Maps one raw row and shape-checks it. Raises `MalformedRowError` for
    either step -- the single entry point `main.py` calls per row."""
    mapped = MAPPERS[resource_type](raw_row)
    validate_shape(resource_type, mapped)
    return mapped
