import pytest

from services.data_service.resource_rules import RowRejected, natural_key, parse_row


def test_valid_patient_row_parses():
    row = {
        "patient_id": "P1",
        "first_name": "A",
        "last_name": "B",
        "date_of_birth": "1990-01-01",
        "gender": "F",
        "phone": "555",
        "language": "en",
    }
    parsed = parse_row("patients", row)
    assert parsed["date_of_birth"].isoformat() == "1990-01-01"
    assert parsed["pcp_provider_name"] is None


def test_pcp_provider_name_is_optional():
    row = {
        "patient_id": "P1",
        "first_name": "A",
        "last_name": "B",
        "date_of_birth": "1990-01-01",
        "gender": "F",
        "phone": "555",
        "language": "en",
        "pcp_provider_name": "Dr Smith",
    }
    assert parse_row("patients", row)["pcp_provider_name"] == "Dr Smith"


def test_missing_required_field_rejected():
    with pytest.raises(RowRejected):
        parse_row("patients", {"patient_id": "P1"})


def test_bad_date_rejected():
    row = {"patient_id": "P1", "icd_code": "E11", "description": "x", "diagnosed_date": "not-a-date"}
    with pytest.raises(RowRejected):
        parse_row("diagnoses", row)


def test_lab_result_value_must_be_numeric():
    row = {"patient_id": "P1", "test_name": "HbA1c", "result_value": "oops", "result_date": "2024-01-01"}
    with pytest.raises(RowRejected):
        parse_row("labs", row)


def test_lab_result_value_parses_as_float():
    row = {"patient_id": "P1", "test_name": "HbA1c", "result_value": "9.2", "result_date": "2024-01-01"}
    assert parse_row("labs", row)["result_value"] == 9.2


def test_unknown_resource_type_rejected():
    with pytest.raises(RowRejected):
        parse_row("bogus", {})


def test_natural_key_for_encounter_matches_the_dedup_key():
    parsed = parse_row(
        "encounters",
        {"patient_id": "P0231", "specialty": "Cardiology", "encounter_date": "2024-10-02", "provider_name": "Dr X"},
    )
    assert natural_key("encounters", parsed) == "P0231|Cardiology|2024-10-02|Dr X"


def test_natural_key_for_patient_is_just_the_id():
    parsed = parse_row(
        "patients",
        {
            "patient_id": "P1",
            "first_name": "A",
            "last_name": "B",
            "date_of_birth": "1990-01-01",
            "gender": "F",
            "phone": "555",
            "language": "en",
        },
    )
    assert natural_key("patients", parsed) == "P1"
