import pytest

from libs.common.errors import IllegalTransitionError
from services.data_service.task_state import next_status


def test_open_to_in_progress_on_claim():
    assert next_status("open", "claim") == "in_progress"


def test_in_progress_to_completed_on_complete():
    assert next_status("in_progress", "complete") == "completed"


def test_in_progress_to_declined_on_decline():
    assert next_status("in_progress", "decline") == "declined"


def test_in_progress_to_open_on_snooze():
    assert next_status("in_progress", "snooze") == "open"


def test_open_and_in_progress_can_close():
    assert next_status("open", "close") == "closed"
    assert next_status("in_progress", "close") == "closed"


@pytest.mark.parametrize(
    ("status", "action"),
    [
        ("open", "complete"),
        ("open", "decline"),
        ("open", "snooze"),
        ("completed", "claim"),
        ("declined", "claim"),
        ("closed", "claim"),
        ("in_progress", "claim"),
        ("completed", "close"),
        ("declined", "close"),
    ],
)
def test_illegal_transitions_rejected(status, action):
    with pytest.raises(IllegalTransitionError):
        next_status(status, action)
