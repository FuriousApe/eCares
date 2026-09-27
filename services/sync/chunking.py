"""Splits a row sequence into fixed-size, order-stable chunks.

Kept separate from `main.py` because both the chunk contents and the
resulting `chunk_number` (its 0-based index) have to be deterministic for
retries -- `UpsertFactsRequest.chunk_number` combined with `run_id` and
`resource_type` is what makes a retried chunk a no-op on the Data Service
side (CLAUDE.md decision #2), so the same input must always split the same
way.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator


def chunked(items: Iterable, size: int) -> Iterator[list]:
    if size <= 0:
        raise ValueError(f"chunk size must be positive, got {size}")
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
