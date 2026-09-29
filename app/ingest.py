"""One-time local CSV load. ~300 patients -- read every row, insert, done.
No staging tables, no chunking, no hashing (see models.py's own docstring
for why that's fine at this scale)."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Diagnosis, Encounter, Lab, Patient

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _date(s: str) -> date:
    return date.fromisoformat(s)


def _rows(name: str):
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def ingest_all(session: Session) -> None:
    for row in _rows("patients.csv"):
        session.add(
            Patient(
                patient_id=row["patient_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                date_of_birth=_date(row["date_of_birth"]),
                gender=row["gender"],
                phone=row["phone"],
                language=row["language"],
                pcp_provider_name=row["pcp_provider_name"] or None,
            )
        )

    for row in _rows("diagnoses.csv"):
        session.add(
            Diagnosis(
                patient_id=row["patient_id"],
                icd_code=row["icd_code"],
                description=row["description"],
                diagnosed_date=_date(row["diagnosed_date"]),
            )
        )

    for row in _rows("labs.csv"):
        session.add(
            Lab(
                patient_id=row["patient_id"],
                test_name=row["test_name"],
                result_value=float(row["result_value"]),
                result_date=_date(row["result_date"]),
            )
        )

    for row in _rows("encounters.csv"):
        session.add(
            Encounter(
                patient_id=row["patient_id"],
                specialty=row["specialty"],
                encounter_date=_date(row["encounter_date"]),
                provider_name=row["provider_name"],
            )
        )

    session.commit()
