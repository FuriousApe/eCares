"""SaveEvaluationResult against a SQLite session.

Covers: exactly-once on a repeated idempotency key, a declined+snoozed key
producing no new task, a new task appearing once the snooze passes, and the
per-need close-resolution wiring (upcoming_visit / not_eligible) end to end.

`patient_eval_state` row locking (`SELECT ... FOR UPDATE`) is exercised
structurally here (the code path always goes through
`db.maybe_for_update`), but real concurrent-writer locking needs MySQL and
is out of scope for a SQLite unit test — see ASSUMPTIONS.md. Likewise, the
P0087 exact-cadence-boundary check ("180 days is not overdue") is the
engine's `due_date` computation, not something this service computes, so
it isn't re-tested here.
"""

from __future__ import annotations

from datetime import date, datetime

from services.data_service.models import Enrollment, Need, Patient, PatientEvalState, Task
from services.data_service.repositories import evaluation as eval_repo

AS_OF = date(2026, 4, 8)


def _patient(session, patient_id="P1"):
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
    session.flush()


def _program_result(program_id="diabetes_management", eligible=True, tier="high_risk", needs=None, version=1):
    return {
        "program_id": program_id,
        "program_version": version,
        "eligible": eligible,
        "tier": tier,
        "needs": needs or [],
    }


def _need(
    specialty="Endocrinology",
    decision="scheduling",
    due_date=None,
    has_upcoming=False,
    last_visit_date=None,
    cadence_days=90,
):
    return {
        "specialty": specialty,
        "cadence_days": cadence_days,
        "last_visit_date": last_visit_date,
        "due_date": due_date,
        "has_upcoming": has_upcoming,
        "decision": decision,
    }


def _save(session, key="k1", program_results=None, next_eval_at=None):
    return eval_repo.save_evaluation_result(
        session,
        patient_id="P1",
        idempotency_key=key,
        program_results=program_results or [],
        evaluated_at=datetime(2026, 4, 8),
        next_eval_at_candidate=next_eval_at,
        request_id="r1",
        as_of_date=AS_OF,
    )


def test_scheduling_task_created_when_none_exists(session):
    _patient(session)
    pr = _program_result(needs=[_need(due_date=date(2026, 5, 1))])
    result = _save(session, program_results=[pr])
    assert result == {"applied": True, "tasks_created": 1, "tasks_closed": 0}
    task = session.query(Task).one()
    assert task.status == "open"
    assert task.task_type == "scheduling"


def test_same_idempotency_key_applies_nothing_the_second_time(session):
    _patient(session)
    pr = _program_result(needs=[_need(due_date=date(2026, 5, 1))])
    _save(session, key="k1", program_results=[pr])
    result2 = _save(session, key="k1", program_results=[pr])
    assert result2 == {"applied": False, "tasks_created": 0, "tasks_closed": 0}
    assert session.query(Task).count() == 1


def test_different_idempotency_key_is_applied_again(session):
    _patient(session)
    pr = _program_result(needs=[_need(specialty="Cardiology", decision="no_task")])
    result = _save(session, key="k2", program_results=[pr])
    assert result["applied"] is True


def test_declined_and_still_snoozed_key_creates_no_task(session):
    _patient(session)
    session.add(
        Task(
            patient_id="P1",
            program_id="diabetes_management",
            specialty="Endocrinology",
            task_type="scheduling",
            status="declined",
            snooze_until=date(2026, 5, 1),
            program_version=1,
            version=2,
        )
    )
    session.flush()
    pr = _program_result(needs=[_need(due_date=date(2026, 4, 1))])
    result = _save(session, program_results=[pr])
    assert result["tasks_created"] == 0
    open_count = session.query(Task).filter(Task.status.in_(("open", "in_progress"))).count()
    assert open_count == 0


def test_task_created_once_the_snooze_has_passed(session):
    _patient(session)
    session.add(
        Task(
            patient_id="P1",
            program_id="diabetes_management",
            specialty="Endocrinology",
            task_type="scheduling",
            status="declined",
            snooze_until=date(2026, 4, 1),  # already before AS_OF
            program_version=1,
            version=2,
        )
    )
    session.flush()
    pr = _program_result(needs=[_need(due_date=date(2026, 4, 1))])
    result = _save(session, program_results=[pr])
    assert result["tasks_created"] == 1


def test_matching_open_task_is_left_untouched(session):
    _patient(session)
    session.add(
        Task(
            patient_id="P1",
            program_id="diabetes_management",
            specialty="Endocrinology",
            task_type="scheduling",
            status="open",
            program_version=1,
            version=1,
        )
    )
    session.flush()
    pr = _program_result(needs=[_need(due_date=date(2026, 5, 1))])
    result = _save(session, program_results=[pr])
    assert result["tasks_created"] == 0
    assert result["tasks_closed"] == 0
    task = session.query(Task).one()
    assert task.version == 1  # no-op: no version bump


def test_open_task_due_date_untouched_by_small_deviation(session):
    _patient(session)
    session.add(
        Task(
            patient_id="P1",
            program_id="diabetes_management",
            specialty="Endocrinology",
            task_type="scheduling",
            status="open",
            due_date=date(2026, 4, 1),
            program_version=1,
            version=1,
        )
    )
    session.flush()
    # 30 days off -- inside the hysteresis band, should not retarget.
    pr = _program_result(needs=[_need(due_date=date(2026, 5, 1))])
    _save(session, program_results=[pr])
    task = session.query(Task).one()
    assert task.due_date == date(2026, 4, 1)
    assert task.version == 1


def test_open_task_due_date_retargeted_past_deviation_threshold(session):
    _patient(session)
    session.add(
        Task(
            patient_id="P1",
            program_id="diabetes_management",
            specialty="Endocrinology",
            task_type="scheduling",
            status="open",
            due_date=date(2026, 4, 1),
            program_version=1,
            version=1,
        )
    )
    session.flush()
    # 90 days off -- past the 60-day hysteresis band, should retarget in place.
    pr = _program_result(needs=[_need(due_date=date(2026, 7, 1))])
    _save(session, program_results=[pr])
    task = session.query(Task).one()
    assert task.due_date == date(2026, 7, 1)
    assert task.version == 2


def test_no_task_decision_closes_open_task_with_upcoming_visit(session):
    _patient(session)
    task = Task(
        patient_id="P1",
        program_id="diabetes_management",
        specialty="Cardiology",
        task_type="scheduling",
        status="open",
        program_version=1,
        version=1,
    )
    session.add(task)
    session.flush()
    pr = _program_result(needs=[_need(specialty="Cardiology", decision="no_task", has_upcoming=True)])
    result = _save(session, program_results=[pr])
    assert result["tasks_closed"] == 1
    session.flush()  # save_evaluation_result relies on session_scope's commit
    session.refresh(task)  # to flush in production; refresh() would otherwise
    assert task.status == "closed"  # discard the still-pending change.
    assert task.resolution == "upcoming_visit"


def test_referral_task_closes_visit_found_when_a_first_visit_appears(session):
    _patient(session)
    task = Task(
        patient_id="P1",
        program_id="diabetes_management",
        specialty="Endocrinology",
        task_type="referral",
        status="open",
        program_version=1,
        version=1,
    )
    session.add(task)
    session.flush()
    pr = _program_result(
        needs=[_need(specialty="Endocrinology", decision="no_task", last_visit_date=date(2026, 3, 1))]
    )
    result = _save(session, program_results=[pr])
    assert result["tasks_closed"] == 1
    session.flush()
    session.refresh(task)
    assert task.resolution == "visit_found"


def test_program_no_longer_eligible_closes_every_open_task_as_not_eligible(session):
    _patient(session)
    task = Task(
        patient_id="P1",
        program_id="diabetes_management",
        specialty="Endocrinology",
        task_type="scheduling",
        status="open",
        program_version=1,
        version=1,
    )
    session.add(task)
    session.add(
        Enrollment(patient_id="P1", program_id="diabetes_management", tier="low_risk", program_version=1, evaluated_at=datetime(2026, 1, 1))
    )
    session.flush()
    pr = _program_result(eligible=False, tier=None, needs=[])
    result = _save(session, program_results=[pr])
    assert result["tasks_closed"] == 1
    session.flush()
    session.refresh(task)
    assert task.status == "closed"
    assert task.resolution == "not_eligible"
    assert session.get(Enrollment, ("P1", "diabetes_management")) is None


def test_specialty_dropped_from_new_tier_closes_task_as_tier_changed(session):
    _patient(session)
    task = Task(
        patient_id="P1",
        program_id="diabetes_management",
        specialty="Cardiology",
        task_type="scheduling",
        status="open",
        program_version=1,
        version=1,
    )
    session.add(task)
    session.add(
        Enrollment(patient_id="P1", program_id="diabetes_management", tier="high_risk", program_version=1, evaluated_at=datetime(2026, 1, 1))
    )
    # A prior evaluation (high_risk tier) is what would have created this
    # open task, and it always upserts a matching `needs` row alongside it —
    # the "stale need" diff below only fires for specialties the *stored*
    # needs table remembers, so a realistic fixture needs this row too.
    session.add(
        Need(patient_id="P1", program_id="diabetes_management", specialty="Cardiology", cadence_days=90)
    )
    session.flush()
    # New evaluation: tier dropped to moderate, and Cardiology is no longer
    # in the needs list at all (not even as decision=no_task).
    pr = _program_result(tier="moderate", needs=[_need(specialty="Endocrinology", decision="no_task")])
    result = _save(session, program_results=[pr])
    assert result["tasks_closed"] == 1
    session.flush()
    session.refresh(task)
    assert task.resolution == "tier_changed"


def test_next_eval_at_folds_in_declined_snooze_alongside_engine_candidate(session):
    _patient(session)
    session.add(
        Task(
            patient_id="P1",
            program_id="diabetes_management",
            specialty="Endocrinology",
            task_type="scheduling",
            status="declined",
            snooze_until=date(2026, 5, 1),  # still active as of AS_OF
            program_version=1,
            version=2,
        )
    )
    session.flush()
    pr = _program_result(needs=[_need(due_date=date(2026, 4, 1))])
    # Engine's own candidate is later than the snooze recheck date, so the
    # overall minimum should come from the snooze (2026-05-01 + 1 day).
    result = _save(session, program_results=[pr], next_eval_at=date(2026, 12, 1))
    assert result["tasks_created"] == 0
    state = session.get(PatientEvalState, "P1")
    assert state.last_idempotency_key == "k1"
    assert state.next_eval_at == date(2026, 5, 2)


def test_next_eval_at_uses_engine_candidate_when_it_is_the_minimum(session):
    _patient(session)
    pr = _program_result(needs=[_need(specialty="Cardiology", decision="no_task")])
    _save(session, program_results=[pr], next_eval_at=date(2026, 6, 1))
    state = session.get(PatientEvalState, "P1")
    assert state.next_eval_at == date(2026, 6, 1)
