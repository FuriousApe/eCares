"""ClaimTask/CompleteTask/DeclineTask/SnoozeTask against a SQLite session.

Covers: stale version -> VersionConflictError, illegal transition ->
IllegalTransitionError, role visibility -> NotFoundError (never a 403), and
the happy path field effects the plan's state table specifies.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from libs.common.errors import IllegalTransitionError, NotFoundError, VersionConflictError
from services.data_service.models import Patient, Task
from services.data_service.repositories import tasks as tasks_repo

AS_OF = date(2026, 4, 8)


def _role(allowed=("scheduling", "referral"), user_id="u1", role="clinical"):
    return SimpleNamespace(allowed_task_types=list(allowed), user_id=user_id, role=role)


def _make_patient(session, patient_id="P1"):
    session.add(
        Patient(
            patient_id=patient_id,
            first_name="A",
            last_name="B",
            date_of_birth=date(1990, 1, 1),
            gender="F",
            phone="555",
            language="en",
            row_hash="x",
        )
    )


def _make_task(session, **overrides):
    defaults = dict(
        patient_id="P1",
        program_id="diabetes_management",
        specialty="Endocrinology",
        task_type="scheduling",
        status="open",
        program_version=1,
        version=1,
    )
    defaults.update(overrides)
    task = Task(**defaults)
    session.add(task)
    session.flush()
    return task


def test_claim_open_task_sets_assigned_to_and_bumps_version(session):
    _make_patient(session)
    task = _make_task(session)
    result = tasks_repo.claim_task(
        session, task_id=task.task_id, version=1, role_filter=_role(), request_id="r1", as_of_date=AS_OF
    )
    assert result["status"] == "in_progress"
    assert result["assigned_to"] == "u1"
    assert result["version"] == 2


def test_claim_with_stale_version_raises_version_conflict(session):
    _make_patient(session)
    task = _make_task(session)
    with pytest.raises(VersionConflictError):
        tasks_repo.claim_task(
            session, task_id=task.task_id, version=99, role_filter=_role(), request_id="r1", as_of_date=AS_OF
        )


def test_claiming_an_already_in_progress_task_is_illegal(session):
    _make_patient(session)
    task = _make_task(session, status="in_progress", assigned_to="someone")
    with pytest.raises(IllegalTransitionError):
        tasks_repo.claim_task(
            session, task_id=task.task_id, version=1, role_filter=_role(), request_id="r1", as_of_date=AS_OF
        )


def test_completing_an_open_task_is_illegal(session):
    _make_patient(session)
    task = _make_task(session, status="open")
    with pytest.raises(IllegalTransitionError):
        tasks_repo.complete_task(
            session,
            task_id=task.task_id,
            version=1,
            resolution="booked",
            note=None,
            role_filter=_role(),
            request_id="r1",
            as_of_date=AS_OF,
        )


def test_complete_in_progress_task_sets_resolution(session):
    _make_patient(session)
    task = _make_task(session, status="in_progress")
    result = tasks_repo.complete_task(
        session,
        task_id=task.task_id,
        version=1,
        resolution="booked",
        note="all set",
        role_filter=_role(),
        request_id="r1",
        as_of_date=AS_OF,
    )
    assert result["status"] == "completed"
    assert result["resolution"] == "booked"


def test_decline_sets_snooze_until_default_90_days(session):
    _make_patient(session)
    task = _make_task(session, status="in_progress")
    result = tasks_repo.decline_task(
        session,
        task_id=task.task_id,
        version=1,
        reason="not interested",
        snooze_days=0,
        role_filter=_role(),
        request_id="r1",
        as_of_date=AS_OF,
        default_snooze_days=90,
    )
    assert result["status"] == "declined"
    assert result["snooze_until"] == (AS_OF + timedelta(days=90)).isoformat()


def test_decline_honors_an_explicit_snooze_days(session):
    _make_patient(session)
    task = _make_task(session, status="in_progress")
    result = tasks_repo.decline_task(
        session,
        task_id=task.task_id,
        version=1,
        reason="not now",
        snooze_days=30,
        role_filter=_role(),
        request_id="r1",
        as_of_date=AS_OF,
        default_snooze_days=90,
    )
    assert result["snooze_until"] == (AS_OF + timedelta(days=30)).isoformat()


def test_snooze_returns_task_to_open_and_clears_assignment(session):
    _make_patient(session)
    task = _make_task(session, status="in_progress", assigned_to="u1")
    until = date(2026, 5, 1)
    result = tasks_repo.snooze_task(
        session,
        task_id=task.task_id,
        version=1,
        until=until,
        reason="call back later",
        role_filter=_role(),
        request_id="r1",
        as_of_date=AS_OF,
    )
    assert result["status"] == "open"
    assert result["snooze_until"] == "2026-05-01"
    assert result["assigned_to"] is None


def test_scheduler_role_cannot_see_a_referral_task_gets_not_found_not_forbidden(session):
    _make_patient(session)
    task = _make_task(session, task_type="referral")
    with pytest.raises(NotFoundError):
        tasks_repo.claim_task(
            session,
            task_id=task.task_id,
            version=1,
            role_filter=_role(allowed=("scheduling",)),
            request_id="r1",
            as_of_date=AS_OF,
        )


def test_claiming_a_missing_task_raises_not_found(session):
    _make_patient(session)
    with pytest.raises(NotFoundError):
        tasks_repo.claim_task(
            session, task_id=999, version=1, role_filter=_role(), request_id="r1", as_of_date=AS_OF
        )
