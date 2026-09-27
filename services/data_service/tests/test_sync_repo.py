"""StartSyncRun/UpsertFacts/CompleteSyncRun against a SQLite session.

Covers: the deferred patients FK check, the P0231-style duplicate natural
key collapsing to one row, a retried chunk being a no-op (not an append),
and a second identical run reporting zero changed patients.
"""

from __future__ import annotations

from services.data_service.models import Diagnosis, Encounter, Patient, StagingRow, SyncQuarantine
from services.data_service.repositories import sync as sync_repo

_PATIENT_ROW = {
    "patient_id": "P1",
    "first_name": "A",
    "last_name": "B",
    "date_of_birth": "1990-01-01",
    "gender": "F",
    "phone": "555",
    "language": "en",
}


def test_patients_then_diagnoses_promote_to_live_tables(session):
    run_id = sync_repo.start_sync_run(session, "csv")
    session.flush()

    accepted, rejected = sync_repo.upsert_facts(
        session, run_id=run_id, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW]
    )
    assert accepted == 1
    assert rejected == []

    accepted, rejected = sync_repo.upsert_facts(
        session,
        run_id=run_id,
        resource_type="diagnoses",
        chunk_number=1,
        rows=[{"patient_id": "P1", "icd_code": "E11", "description": "Diabetes", "diagnosed_date": "2024-01-01"}],
    )
    assert accepted == 1

    result = sync_repo.complete_sync_run(session, run_id=run_id, status="completed")
    assert result["changed_patient_ids"] == ["P1"]
    assert session.query(Patient).count() == 1
    assert session.query(Diagnosis).count() == 1
    assert result["counts_json"]


def test_diagnosis_referencing_unknown_patient_is_quarantined_at_complete(session):
    run_id = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(
        session,
        run_id=run_id,
        resource_type="diagnoses",
        chunk_number=1,
        rows=[{"patient_id": "GHOST", "icd_code": "E11", "description": "x", "diagnosed_date": "2024-01-01"}],
    )
    result = sync_repo.complete_sync_run(session, run_id=run_id, status="completed")
    assert result["changed_patient_ids"] == []
    assert session.query(Diagnosis).count() == 0
    assert session.query(SyncQuarantine).filter_by(resource_type="diagnoses").count() == 1


def test_row_that_fails_validation_is_quarantined_immediately_not_staged(session):
    run_id = sync_repo.start_sync_run(session, "csv")
    session.flush()
    accepted, rejected = sync_repo.upsert_facts(
        session,
        run_id=run_id,
        resource_type="diagnoses",
        chunk_number=1,
        rows=[{"patient_id": "P1", "icd_code": "E11", "description": "x", "diagnosed_date": "not-a-date"}],
    )
    assert accepted == 0
    assert len(rejected) == 1
    assert session.query(StagingRow).filter_by(run_id=run_id).count() == 0
    assert session.query(SyncQuarantine).filter_by(run_id=run_id).count() == 1


def test_duplicate_natural_key_within_one_run_collapses_to_one_row(session):
    # Same setup as the plan's P0231 / 2024-10-02 duplicate encounter case.
    run_id = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(session, run_id=run_id, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW])
    sync_repo.upsert_facts(
        session,
        run_id=run_id,
        resource_type="encounters",
        chunk_number=1,
        rows=[
            {"patient_id": "P1", "specialty": "Cardiology", "encounter_date": "2024-10-02", "provider_name": "Dr X"},
            {"patient_id": "P1", "specialty": "Cardiology", "encounter_date": "2024-10-02", "provider_name": "Dr X"},
        ],
    )
    sync_repo.complete_sync_run(session, run_id=run_id, status="completed")
    assert session.query(Encounter).count() == 1


def test_retried_chunk_replaces_staging_rows_instead_of_appending(session):
    run_id = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(session, run_id=run_id, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW])
    sync_repo.upsert_facts(session, run_id=run_id, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW])
    count = (
        session.query(StagingRow)
        .filter_by(run_id=run_id, resource_type="patients", chunk_number=1)
        .count()
    )
    assert count == 1


def test_second_identical_run_reports_zero_changed_patients(session):
    run1 = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(session, run_id=run1, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW])
    sync_repo.complete_sync_run(session, run_id=run1, status="completed")

    run2 = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(session, run_id=run2, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW])
    result = sync_repo.complete_sync_run(session, run_id=run2, status="completed")
    assert result["changed_patient_ids"] == []


def test_changed_field_on_rerun_is_reported_as_changed(session):
    run1 = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(session, run_id=run1, resource_type="patients", chunk_number=1, rows=[_PATIENT_ROW])
    sync_repo.complete_sync_run(session, run_id=run1, status="completed")

    updated_row = dict(_PATIENT_ROW, last_name="Changed")
    run2 = sync_repo.start_sync_run(session, "csv")
    session.flush()
    sync_repo.upsert_facts(session, run_id=run2, resource_type="patients", chunk_number=1, rows=[updated_row])
    result = sync_repo.complete_sync_run(session, run_id=run2, status="completed")
    assert result["changed_patient_ids"] == ["P1"]
    assert session.get(Patient, "P1").last_name == "Changed"
