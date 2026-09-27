"""Mapper unit tests: CSV row dict -> canonical field dict, plus the shape
check's edge cases from the plan.
"""

from __future__ import annotations

import pytest

from services.sync.mappers import (
    MalformedRowError,
    map_and_validate,
    map_diagnosis,
    map_encounter,
    map_lab,
    map_patient,
)

PATIENT_ROW = {
    "patient_id": "P0018",
    "first_name": "Jane",
    "last_name": "Doe",
    "date_of_birth": "1980-01-02",
    "gender": "F",
    "phone": "555-0100",
    "language": "English",
    "pcp_provider_name": "Dr. Amy Martinez",
}
DIAGNOSIS_ROW = {
    "patient_id": "P0028",
    "icd_code": "E11.40",
    "description": "Type 2 diabetes with diabetic neuropathy",
    "diagnosed_date": "2024-12-13",
}
LAB_ROW = {
    "patient_id": "P0002",
    "test_name": "HbA1c",
    "result_value": "13.1",
    "result_date": "2025-12-24",
}
ENCOUNTER_ROW = {
    "patient_id": "P0001",
    "specialty": "PCP",
    "encounter_date": "2025-12-31",
    "provider_name": "Dr. Amy Martinez",
}


def test_map_patient_is_a_straight_passthrough():
    assert map_patient(PATIENT_ROW) == PATIENT_ROW


def test_map_diagnosis_is_a_straight_passthrough():
    assert map_diagnosis(DIAGNOSIS_ROW) == DIAGNOSIS_ROW


def test_map_lab_is_a_straight_passthrough():
    assert map_lab(LAB_ROW) == LAB_ROW


def test_map_encounter_is_a_straight_passthrough():
    assert map_encounter(ENCOUNTER_ROW) == ENCOUNTER_ROW


def test_missing_pcp_provider_name_maps_through_as_blank_not_rejected():
    """The plan: 'a missing PCP name is not "no PCP history"' -- PCP history
    comes from encounters, so sync must not reject the row; it passes the
    blank through faithfully for the Data Service to decide what it means."""
    row = dict(PATIENT_ROW)
    row["pcp_provider_name"] = ""
    mapped = map_patient(row)
    assert mapped["pcp_provider_name"] == ""
    # Must not raise -- a blank PCP name is not a shape problem.
    map_and_validate("patients", row)


def test_absent_pcp_provider_name_column_also_maps_through_as_blank():
    row = {k: v for k, v in PATIENT_ROW.items() if k != "pcp_provider_name"}
    mapped = map_patient(row)
    assert mapped["pcp_provider_name"] == ""


@pytest.mark.parametrize(
    "resource_type, row",
    [
        ("patients", PATIENT_ROW),
        ("diagnoses", DIAGNOSIS_ROW),
        ("labs", LAB_ROW),
        ("encounters", ENCOUNTER_ROW),
    ],
)
def test_missing_required_column_raises(resource_type, row):
    broken = dict(row)
    del broken["patient_id"]
    with pytest.raises(MalformedRowError):
        map_and_validate(resource_type, broken)


@pytest.mark.parametrize(
    "resource_type, row, date_field",
    [
        ("patients", PATIENT_ROW, "date_of_birth"),
        ("diagnoses", DIAGNOSIS_ROW, "diagnosed_date"),
        ("labs", LAB_ROW, "result_date"),
        ("encounters", ENCOUNTER_ROW, "encounter_date"),
    ],
)
@pytest.mark.parametrize("bad_date", ["not-a-date", "13/25/2024", "", "2024/12/13"])
def test_malformed_date_raises(resource_type, row, date_field, bad_date):
    broken = dict(row)
    broken[date_field] = bad_date
    with pytest.raises(MalformedRowError):
        map_and_validate(resource_type, broken)


def test_valid_date_shape_passes_all_resources():
    for resource_type, row in [
        ("patients", PATIENT_ROW),
        ("diagnoses", DIAGNOSIS_ROW),
        ("labs", LAB_ROW),
        ("encounters", ENCOUNTER_ROW),
    ]:
        map_and_validate(resource_type, row)  # must not raise


def test_blank_patient_id_raises():
    broken = dict(ENCOUNTER_ROW)
    broken["patient_id"] = "  "
    with pytest.raises(MalformedRowError):
        map_and_validate("encounters", broken)
