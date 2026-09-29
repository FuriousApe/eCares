"""Calendar-month arithmetic. Ported verbatim from the `main` branch's
`libs/common/dates.py` -- plain stdlib, no dependency earns its keep for
four functions, and copying them avoids this lean build depending on the
`main` branch's package layout at all."""

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


def is_past(d: date, as_of_date: date) -> bool:
    """A visit dated on or before the as-of date is past; a later one is
    upcoming. One day is never both."""
    return d <= as_of_date


def add_days(d: date, days: int) -> date:
    return d + timedelta(days=days)
