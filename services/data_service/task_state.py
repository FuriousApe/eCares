"""The task state machine, as a pure function — no DB, no I/O.

Kept separate from the repository so the transition table itself is unit
testable without a database (`tests/test_task_state.py`), and so the exact
rules from the plan's "MVP task states" table live in exactly one place.

Transitions NOT covered here: open/in_progress -> closed. That one is
engine-driven (the diff in `SaveEvaluationResult`), never a direct RPC
caller action, so it is validated separately in `repositories/evaluation.py`.
"""

from __future__ import annotations

from libs.common.errors import IllegalTransitionError

ACTIONS = ("claim", "complete", "decline", "snooze", "close")

# (current_status, action) -> new_status. Anything absent is illegal.
_TRANSITIONS: dict[tuple[str, str], str] = {
    ("open", "claim"): "in_progress",
    ("in_progress", "complete"): "completed",
    ("in_progress", "decline"): "declined",
    ("in_progress", "snooze"): "open",
    ("open", "close"): "closed",
    ("in_progress", "close"): "closed",
}


def next_status(current_status: str, action: str) -> str:
    """Returns the resulting status, or raises `IllegalTransitionError`."""
    key = (current_status, action)
    if key not in _TRANSITIONS:
        raise IllegalTransitionError(
            f"cannot {action} a task in status {current_status!r}"
        )
    return _TRANSITIONS[key]
