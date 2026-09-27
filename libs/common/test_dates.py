from datetime import date

from libs.common.dates import days_overdue, is_past, months_before


def test_months_before_plain():
    assert months_before(date(2026, 4, 8), 6) == date(2025, 10, 8)


def test_months_before_clamps_short_month():
    assert months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_months_before_leap_year():
    assert months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)


def test_days_overdue_strict_boundary_not_overdue():
    # P0087: a gap of exactly the cadence is not overdue (strict >).
    as_of = date(2026, 4, 8)
    due = as_of  # due == as_of means exactly on the cadence boundary
    assert days_overdue(due, as_of) == 0  # due today counts as overdue-eligible day 0
    assert days_overdue(date(2026, 4, 9), as_of) is None  # due in the future: not overdue


def test_days_overdue_none_when_no_due_date():
    assert days_overdue(None, date(2026, 4, 8)) is None


def test_is_past_boundary_counts_as_past():
    as_of = date(2026, 4, 8)
    assert is_past(as_of, as_of) is True
    assert is_past(date(2026, 4, 9), as_of) is False


if __name__ == "__main__":
    test_months_before_plain()
    test_months_before_clamps_short_month()
    test_months_before_leap_year()
    test_days_overdue_strict_boundary_not_overdue()
    test_days_overdue_none_when_no_due_date()
    test_is_past_boundary_counts_as_past()
    print("OK")
