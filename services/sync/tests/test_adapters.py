"""CsvAdapter tests against small temp CSVs (never the real 300-row files)."""

from __future__ import annotations

from services.sync.adapters import CsvAdapter


def test_reads_rows_in_file_order(tmp_path):
    (tmp_path / "patients.csv").write_text(
        "patient_id,first_name\nP0001,Robert\nP0002,Richard\n", encoding="utf-8"
    )
    adapter = CsvAdapter(tmp_path)

    rows = list(adapter.rows("patients"))

    assert [r[1]["patient_id"] for r in rows] == ["P0001", "P0002"]
    assert all(resource_type == "patients" for resource_type, _ in rows)


def test_row_is_a_plain_dict_keyed_by_header(tmp_path):
    (tmp_path / "labs.csv").write_text(
        "patient_id,test_name,result_value,result_date\nP0002,HbA1c,13.1,2025-12-24\n",
        encoding="utf-8",
    )
    adapter = CsvAdapter(tmp_path)

    [(resource_type, row)] = list(adapter.rows("labs"))

    assert resource_type == "labs"
    assert row == {
        "patient_id": "P0002",
        "test_name": "HbA1c",
        "result_value": "13.1",
        "result_date": "2025-12-24",
    }


def test_empty_csv_yields_no_rows(tmp_path):
    (tmp_path / "diagnoses.csv").write_text(
        "patient_id,icd_code,description,diagnosed_date\n", encoding="utf-8"
    )
    adapter = CsvAdapter(tmp_path)

    assert list(adapter.rows("diagnoses")) == []
