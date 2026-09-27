"""Loads the real `ecares/data/*.csv` files (skipped if they're not present)
and checks the row counts the plan's M2 milestone names, plus that every
real row passes the mapper/shape check cleanly (no malformed rows in the
actual data).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.sync.adapters import CsvAdapter
from services.sync.mappers import MalformedRowError, map_and_validate

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

EXPECTED_RAW_COUNTS = {
    "patients": 300,
    "diagnoses": 312,
    "labs": 238,
    # 1159 raw rows: one intentional duplicate (P0231, 2024-10-02) that the
    # Data Service drops on its natural key at CompleteSyncRun, leaving 1158
    # stored -- sync itself does not dedup, it just reads and forwards.
    "encounters": 1159,
}

pytestmark = pytest.mark.skipif(
    not DATA_DIR.is_dir(), reason=f"real data dir not found at {DATA_DIR}"
)


@pytest.mark.parametrize("resource_type, expected_count", EXPECTED_RAW_COUNTS.items())
def test_real_csv_row_counts(resource_type, expected_count):
    adapter = CsvAdapter(DATA_DIR)
    rows = list(adapter.rows(resource_type))
    assert len(rows) == expected_count


@pytest.mark.parametrize("resource_type", EXPECTED_RAW_COUNTS)
def test_real_csv_rows_all_pass_the_shape_check(resource_type):
    adapter = CsvAdapter(DATA_DIR)
    malformed = 0
    for _, raw_row in adapter.rows(resource_type):
        try:
            map_and_validate(resource_type, raw_row)
        except MalformedRowError:
            malformed += 1
    assert malformed == 0


def test_real_encounters_contains_the_known_duplicate():
    adapter = CsvAdapter(DATA_DIR)
    p0231_on_that_date = [
        raw
        for _, raw in adapter.rows("encounters")
        if raw["patient_id"] == "P0231" and raw["encounter_date"] == "2024-10-02"
    ]
    assert len(p0231_on_that_date) == 2, "expected the documented duplicate encounter row"
