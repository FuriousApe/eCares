"""Data Service entrypoint: `main()` is called by the repo's `run.py`
dispatcher when `ROLE=data-service`.

`DS_ROLES` (comma-separated: `interactive`, `bulk`, `relay`) decides which
parts of this process actually run. All three RPC groups are always
registered on the gRPC server regardless — "interactive" vs "bulk" is a
deployment split, not a code split, per the plan (splitting them into
separate containers later is a Compose change). Only the outbox relay is
genuinely conditional: it's a background thread with no RPC surface, so
"don't run this part" for it means "don't start the thread".
"""

from __future__ import annotations

import logging
import signal
from concurrent import futures

import grpc

from libs.common.grpc_gen import dataservice_pb2_grpc
from libs.common.logging import configure_logging
from libs.common.settings import get_settings
from services.data_service.outbox import start_relay_thread
from services.data_service.servicer import DataServiceServicer

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging("data-service")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    dataservice_pb2_grpc.add_DataServiceServicer_to_server(DataServiceServicer(), server)
    address = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_insecure_port(address)
    server.start()
    logger.info("data-service listening on %s (ds_roles=%s)", address, sorted(settings.ds_role_set))

    stop_event = None
    if "relay" in settings.ds_role_set:
        _thread, stop_event = start_relay_thread()
        logger.info("outbox relay thread started")

    def _handle_stop(*_args: object) -> None:
        server.stop(grace=5)
        if stop_event is not None:
            stop_event.set()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
