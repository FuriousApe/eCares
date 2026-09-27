from datetime import date

from services.data_service.evaluation_rules import (
    CLOSE_NOT_ELIGIBLE,
    CLOSE_TIER_CHANGED,
    CLOSE_UPCOMING_VISIT,
    CLOSE_VISIT_FOUND,
    compute_next_eval_at,
    is_snoozed,
    pick_close_resolution,
    snooze_recheck_date,
)


def test_referral_task_closes_visit_found_when_a_past_visit_appears():
    resolution = pick_close_resolution(
        task_type="referral", has_upcoming=False, has_past_visit=True, tier_changed=False, program_eligible=True
    )
    assert resolution == CLOSE_VISIT_FOUND


def test_referral_task_closes_visit_found_when_an_upcoming_visit_appears():
    resolution = pick_close_resolution(
        task_type="referral", has_upcoming=True, has_past_visit=False, tier_changed=False, program_eligible=True
    )
    assert resolution == CLOSE_VISIT_FOUND


def test_scheduling_task_closes_upcoming_visit_over_tier_changed():
    resolution = pick_close_resolution(
        task_type="scheduling", has_upcoming=True, has_past_visit=True, tier_changed=True, program_eligible=True
    )
    assert resolution == CLOSE_UPCOMING_VISIT


def test_scheduling_task_closes_tier_changed():
    resolution = pick_close_resolution(
        task_type="scheduling", has_upcoming=False, has_past_visit=True, tier_changed=True, program_eligible=True
    )
    assert resolution == CLOSE_TIER_CHANGED


def test_not_eligible_is_the_fallback():
    resolution = pick_close_resolution(
        task_type="scheduling", has_upcoming=False, has_past_visit=True, tier_changed=False, program_eligible=False
    )
    assert resolution == CLOSE_NOT_ELIGIBLE


def test_is_snoozed_boundary_is_inclusive_of_the_snooze_until_date():
    assert is_snoozed(date(2026, 4, 8), date(2026, 4, 8)) is True
    assert is_snoozed(date(2026, 4, 8), date(2026, 4, 9)) is False
    assert is_snoozed(None, date(2026, 4, 8)) is False


def test_compute_next_eval_at_takes_the_minimum():
    candidates = [date(2026, 6, 1), date(2026, 5, 1), None, date(2026, 12, 1)]
    assert compute_next_eval_at(candidates) == date(2026, 5, 1)


def test_compute_next_eval_at_is_none_when_no_candidates():
    assert compute_next_eval_at([None, None]) is None


def test_snooze_recheck_date_is_one_day_after_the_snooze_ends():
    assert snooze_recheck_date(date(2026, 4, 8)) == date(2026, 4, 9)
