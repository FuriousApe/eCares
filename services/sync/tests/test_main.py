"""Orchestration tests for `run_sync`, against a fake stub (no live Data
Service) and small temp CSVs (no dependency on the real 300-row files)."""

from __future__ import annotations

import grpc
import pytest

from services.sync.adapters import CsvAdapter
from services.sync.main import run_sync
from services.sync.tests.fake_stub import FakeDataServiceStub

VALID_CSVS = {
    "patients.csv": (
        "patient_id,first_name,last_name,date_of_birth,gender,phone,language,pcp_provider_name\n"
        "P0001,Robert,Scott,2004-02-27,M,555-0001,English,Dr. Amy Martinez\n"
        "P0002,Richard,Ramirez,1989-04-10,M,555-0002,Spanish,\n"
    ),
    "diagnoses.csv": (
        "patient_id,icd_code,description,diagnosed_date\n"
        "P0001,E11.40,Type 2 diabetes,2024-12-13\n"
    ),
    "labs.csv": (
        "patient_id,test_name,result_value,result_date\nP0001,HbA1c,7.2,2025-12-24\n"
    ),
    "encounters.csv": (
        "patient_id,specialty,encounter_date,provider_name\n"
        "P0001,PCP,2025-12-31,Dr. Amy Martinez\n"
        "P0002,PCP,2024-06-12,Dr. Amy Martinez\n"
    ),
}


def _write_csvs(tmp_path, overrides: dict[str, str] | None = None, omit: set[str] | None = None):
    files = dict(VALID_CSVS)
    files.update(overrides or {})
    for name in omit or ():
        files.pop(name, None)
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return CsvAdapter(tmp_path)


def test_happy_path_sends_every_resource_and_completes(tmp_path):
    adapter = _write_csvs(tmp_path)
    stub = FakeDataServiceStub()

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 0
    call_names = [name for name, _ in stub.calls]
    assert call_names[0] == "StartSyncRun"
    assert call_names[-1] == "CompleteSyncRun"
    assert call_names.count("UpsertFacts") == 4  # one per resource, all fit in one chunk

    complete_request = stub.calls[-1][1]
    assert complete_request.status == "completed"

    upsert_resource_types = {req.resource_type for name, req in stub.calls if name == "UpsertFacts"}
    assert upsert_resource_types == {"patients", "diagnoses", "labs", "encounters"}


def test_blank_pcp_provider_name_row_is_still_sent(tmp_path):
    adapter = _write_csvs(tmp_path)
    stub = FakeDataServiceStub()

    run_sync(adapter, stub, chunk_size=10)

    patient_chunk = next(
        req for name, req in stub.calls if name == "UpsertFacts" and req.resource_type == "patients"
    )
    sent_ids = [row.fields["patient_id"] for row in patient_chunk.rows]
    assert sent_ids == ["P0001", "P0002"]  # the blank-PCP row (P0002) was not dropped


def test_malformed_row_is_skipped_but_run_still_completes(tmp_path):
    broken_patients = VALID_CSVS["patients.csv"] + "P0003,Bad,Row,not-a-date,M,555-0003,English,\n"
    adapter = _write_csvs(tmp_path, overrides={"patients.csv": broken_patients})
    stub = FakeDataServiceStub()

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 0
    patient_chunk = next(
        req for name, req in stub.calls if name == "UpsertFacts" and req.resource_type == "patients"
    )
    assert len(patient_chunk.rows) == 2  # the malformed P0003 row never got sent


def test_missing_csv_file_fails_the_run(tmp_path):
    adapter = _write_csvs(tmp_path, omit={"encounters.csv"})
    stub = FakeDataServiceStub()

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 1
    complete_request = stub.calls[-1][1]
    assert complete_request.status == "failed"


def test_data_service_rejected_rows_still_count_as_success(tmp_path):
    adapter = _write_csvs(tmp_path)
    stub = FakeDataServiceStub(
        rejects_first_chunk={"labs": [({"patient_id": "P0001"}, "unknown patient_id")]}
    )

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 0  # a row the Data Service quarantines is not a sync failure


def test_transient_failure_retries_same_chunk_number_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("services.sync.main.time.sleep", lambda _seconds: None)
    adapter = _write_csvs(tmp_path)
    stub = FakeDataServiceStub(fail_upsert_times=2, fail_code=grpc.StatusCode.UNAVAILABLE)

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 0
    patient_attempts = [
        req.chunk_number
        for name, req in stub.calls
        if name == "UpsertFacts" and req.resource_type == "patients"
    ]
    assert patient_attempts == [0, 0, 0]  # same chunk_number on every retry


def test_retries_are_exhausted_and_run_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("services.sync.main.time.sleep", lambda _seconds: None)
    adapter = _write_csvs(tmp_path)
    stub = FakeDataServiceStub(fail_upsert_times=99, fail_code=grpc.StatusCode.UNAVAILABLE)

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 1
    complete_request = stub.calls[-1][1]
    assert complete_request.status == "failed"


def test_non_retryable_error_gives_up_immediately(tmp_path, monkeypatch):
    def _fail_if_called(_seconds):
        pytest.fail("should not sleep")

    monkeypatch.setattr("services.sync.main.time.sleep", _fail_if_called)
    adapter = _write_csvs(tmp_path)
    stub = FakeDataServiceStub(fail_upsert_times=1, fail_code=grpc.StatusCode.INVALID_ARGUMENT)

    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 1


def test_start_sync_run_failure_never_calls_complete(tmp_path):
    adapter = _write_csvs(tmp_path)

    class DeadOnStart(FakeDataServiceStub):
        def StartSyncRun(self, request, metadata=None):
            raise grpc.RpcError("data service unreachable")

    stub = DeadOnStart()
    result = run_sync(adapter, stub, chunk_size=10)

    assert result.exit_code == 1
    assert stub.calls == []  # never even recorded, StartSyncRun raised before that
