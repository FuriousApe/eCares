"""Pure decision logic for `SaveEvaluationResult` — no DB, no I/O.

Kept separate from `repositories/evaluation.py` so the genuinely ambiguous
part of the plan (which resolution a closed task gets) and the `next_eval_at`
minimum are unit-testable in isolation (`tests/test_evaluation_rules.py`).
"""

from __future__ import annotations

from datetime import date, timedelta

CLOSE_VISIT_FOUND = "visit_found"
CLOSE_UPCOMING_VISIT = "upcoming_visit"
CLOSE_TIER_CHANGED = "tier_changed"
CLOSE_NOT_ELIGIBLE = "not_eligible"


def pick_close_resolution(
    *,
    task_type: str,
    has_upcoming: bool,
    has_past_visit: bool,
    tier_changed: bool,
    program_eligible: bool,
) -> str:
    """The plan names `visit_found` explicitly for a referral task whose
    specialty just got its first visit (upcoming or past); otherwise an
    upcoming visit always wins over a tier change, and a tier change wins
    over the generic "not eligible" catch-all. This ordering is this
    project's resolution — see ASSUMPTIONS.md, the plan leaves it open.
    """
    if task_type == "referral" and (has_upcoming or has_past_visit):
        return CLOSE_VISIT_FOUND
    if has_upcoming:
        return CLOSE_UPCOMING_VISIT
    if tier_changed:
        return CLOSE_TIER_CHANGED
    if not program_eligible:
        return CLOSE_NOT_ELIGIBLE
    return CLOSE_NOT_ELIGIBLE  # fallback: nothing else explains "no longer needed"


def is_snoozed(snooze_until: date | None, as_of_date: date) -> bool:
    """A declined task still blocks task creation while its snooze has not
    yet passed. `>=` matches the plan's "the comparison is strict" rule
    applied the other way: the snooze is active through its last day."""
    return snooze_until is not None and snooze_until >= as_of_date


def compute_next_eval_at(candidates: list[date | None]) -> date | None:
    """Earliest future date any of the caller's candidates points to.

    Candidates come from three sources (per the plan): every
    `NeedResult.next_check_candidate`, every `ProgramResult.tier_recheck_at`,
    and `snooze_until + 1 day` for any declined task at a key just
    evaluated. `None` entries (nothing about that fact pattern will flip on
    its own) are ignored.
    """
    real = [c for c in candidates if c is not None]
    return min(real) if real else None


def snooze_recheck_date(snooze_until: date) -> date:
    return snooze_until + timedelta(days=1)
