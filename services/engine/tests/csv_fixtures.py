"""Reads `ecares/data/*.csv` directly (stdlib csv, no pandas) to build a
`PatientSnapshot` for one patient, for tests that check the evaluator against
the plan's named verification patients. Not itself a test module.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from services.engine.evaluator import Diagnosis, Encounter, LabResult, PatientSnapshot, age_as_of

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _read_rows(name: str) -> list[dict]:
    with open(DATA_DIR / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_snapshot(patient_id: str, as_of_date: date) -> PatientSnapshot:
    patients = _read_rows("patients.csv")
    row = next(r for r in patients if r["patient_id"] == patient_id)
    dob = date.fromisoformat(row["date_of_birth"])

    diagnoses = [
        Diagnosis(icd_code=r["icd_code"], diagnosed_date=date.fromisoformat(r["diagnosed_date"]))
        for r in _read_rows("diagnoses.csv")
        if r["patient_id"] == patient_id
    ]
    labs = [
        LabResult(
            test_name=r["test_name"],
            result_value=float(r["result_value"]),
            result_date=date.fromisoformat(r["result_date"]),
        )
        for r in _read_rows("labs.csv")
        if r["patient_id"] == patient_id
    ]
    # P0231's duplicate (patient_id, specialty, encounter_date, provider_name) row is a
    # sync-layer dedup concern (unique key in the `encounters` table), not the evaluator's
    # -- it only affects "how many rows come back", never a decision, since gap/upcoming
    # logic already looks at the *latest*/*earliest* date, not row count. Dedup here so a
    # snapshot built straight from the CSV matches what the Data Service would actually
    # hand the evaluator.
    seen = set()
    encounters = []
    for r in _read_rows("encounters.csv"):
        if r["patient_id"] != patient_id:
            continue
        key = (r["specialty"], r["encounter_date"], r["provider_name"])
        if key in seen:
            continue
        seen.add(key)
        encounter_date = date.fromisoformat(r["encounter_date"])
        encounters.append(
            Encounter(
                specialty=r["specialty"],
                encounter_date=encounter_date,
                is_upcoming=encounter_date > as_of_date,
            )
        )

    return PatientSnapshot(
        patient_id=patient_id,
        age=age_as_of(dob, as_of_date),
        diagnoses=diagnoses,
        labs=labs,
        encounters=encounters,
    )
