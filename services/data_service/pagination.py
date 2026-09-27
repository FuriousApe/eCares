"""Keyset pagination helper.

Ponytail: one supported, stable ascending order per list (`task_id` /
`patient_id`) rather than a general multi-column sort+cursor engine — the
plan's verification checks counts and role filters, not sort order, and a
plain `WHERE pk > cursor ORDER BY pk` is the smallest thing that is actually
correct across pages (no skipped/duplicated rows). `ListTasksRequest.sort`
is accepted but not wired to a different cursor shape; add a composite
cursor (e.g. `due_date|task_id`) if a real UI sort order is needed later.
"""

from __future__ import annotations


def clamp_limit(limit: int, default: int = 50, maximum: int = 200) -> int:
    if limit <= 0:
        return default
    return min(limit, maximum)
