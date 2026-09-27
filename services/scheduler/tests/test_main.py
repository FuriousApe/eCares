"""One small smoke test for the sweep loop: it calls `EnqueueDuePatients`
with the effective as-of date and sleeps between calls. Mocks the gRPC stub
and `time.sleep` (raising on the second sleep to stop the `while True` loop
after exactly one iteration) rather than needing a live Data Service."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from services.scheduler import main as scheduler_main


class _StopLoop(Exception):
    pass


def test_sweep_calls_enqueue_due_patients_with_as_of_date_and_sleeps():
    fake_stub = MagicMock()
    fake_stub.EnqueueDuePatients.return_value = MagicMock(enqueued_count=7)

    with (
        patch.object(scheduler_main, "get_settings") as mock_get_settings,
        patch.object(scheduler_main, "data_service_stub", return_value=fake_stub),
        patch.object(scheduler_main.time, "sleep", side_effect=_StopLoop) as mock_sleep,
        patch.object(scheduler_main, "configure_logging"),
    ):
        settings = mock_get_settings.return_value
        settings.effective_as_of_date.return_value = date(2026, 4, 8)
        settings.scheduler_interval_seconds = 60
        settings.data_service_target = "data-service:50051"

        with pytest.raises(_StopLoop):
            scheduler_main.main()

    request = fake_stub.EnqueueDuePatients.call_args.args[0]
    assert request.as_of_date == "2026-04-08"
    mock_sleep.assert_called_once_with(60)
