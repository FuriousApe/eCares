"""Scheduler entrypoint (`ROLE=scheduler`).

A small timer: every `settings.scheduler_interval_seconds`, ask the Data
Service to enqueue patients whose `next_eval_at` has passed, and log the
count. Deliberately just a `while True: call, sleep` loop -- one fixed
interval doesn't need a cron-expression scheduler.
"""

from __future__ import annotations

import logging
import time

from libs.common.grpc_client import call_metadata, data_service_stub
from libs.common.grpc_gen import dataservice_pb2
from libs.common.logging import configure_logging
from libs.common.settings import get_settings

logger = logging.getLogger("scheduler")


def main() -> None:
    configure_logging("scheduler")
    settings = get_settings()
    stub = data_service_stub(settings.data_service_target)

    while True:
        as_of_date = settings.effective_as_of_date()
        response = stub.EnqueueDuePatients(
            dataservice_pb2.EnqueueDuePatientsRequest(as_of_date=as_of_date.isoformat()),
            metadata=call_metadata(),
        )
        logger.info("enqueued %s due patient(s) as of %s", response.enqueued_count, as_of_date)
        time.sleep(settings.scheduler_interval_seconds)


if __name__ == "__main__":
    main()
