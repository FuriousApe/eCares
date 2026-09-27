"""Integration-suite-only wiring.

Every test collected under `tests/integration/` implicitly depends on
`live_stack` (defined in `tests/conftest.py`) through the autouse fixture
below, so `pytest tests/integration` fails fast with one clear skip reason
when nothing is running, instead of each test hanging on its own timeout.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "slow: exercises real wall-clock waits (Kafka propagation, container restarts)"
    )


@pytest.fixture(autouse=True)
def _require_live_stack(live_stack) -> None:
    """No-op body -- just forces every test in this directory through the
    health-checked `live_stack` fixture."""
