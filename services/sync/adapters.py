"""Source adapters for the sync job.

A `SourceAdapter` yields `(resource_type, raw_row)` tuples for one resource
at a time, in source order. `CsvAdapter` is the only implementation for the
MVP (the FHIR bulk adapter is deferred, per the plan) -- the split exists so
a future adapter only has to satisfy this one small shape, not because the
CSV path itself needs to be pluggable today.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

# Patients first: not required by the Data Service (FK checks are deferred to
# CompleteSyncRun), just the sane load order.
RESOURCE_ORDER: tuple[str, ...] = ("patients", "diagnoses", "labs", "encounters")


class SourceAdapter(Protocol):
    def rows(self, resource_type: str) -> Iterator[tuple[str, dict[str, str]]]:
        """Yield `(resource_type, raw_row)` for every row of one resource."""
        ...


class CsvAdapter:
    """Reads `<data_dir>/<resource_type>.csv`, one DictReader row at a time."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)

    def rows(self, resource_type: str) -> Iterator[tuple[str, dict[str, str]]]:
        path = self.data_dir / f"{resource_type}.csv"
        with path.open(newline="", encoding="utf-8") as f:
            for raw_row in csv.DictReader(f):
                yield resource_type, raw_row
