"""Calendar-month arithmetic shared by the engine and the Data Service, so
"within the last 6 months" means the same date on both sides of the gRPC
call. Plain stdlib — no dependency earns its keep for one function.

`tests/oracle.py` must NOT import this: it is the independent verification
script and has its own equivalent using pandas, on purpose (see CLAUDE.md).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def months_before(d: date, months: int) -> date:
    """`d` minus `months` calendar months, clamping the day to the shorter
    month (e.g. 2026-03-31 minus 1 month -> 2026-02-28)."""
    month_index = d.month - 1 - months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def days_overdue(due_date: date | None, as_of_date: date) -> int | None:
    """Computed at read time, never stored, so nothing changes overnight."""
    if due_date is None or due_date > as_of_date:
        return None
    return (as_of_date - due_date).days


def is_past(d: date, as_of_date: date) -> bool:
    """A visit dated on or before the as-of date is past; a later one is
    upcoming. One day is never both."""
    return d <= as_of_date


def add_days(d: date, days: int) -> date:
    return d + timedelta(days=days)
