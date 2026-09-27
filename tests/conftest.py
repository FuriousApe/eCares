"""Shared fixtures for the live-stack integration suite (`tests/integration/`).

`tests/oracle.py` needs none of this -- it is a standalone script that only
touches the CSVs. Everything here is for tests that talk to a running
`docker compose` stack.

## Host mode vs. container-network mode

Two ways to point this suite at a running stack:

1. **Host mode (the default here).** pytest runs on the *host*
   (`ecares/.venv/Scripts/python.exe -m pytest tests/integration`), talking
   to the stack through the ports `docker-compose.yml` publishes to
   localhost (mysql:3306, redis:6379, kafka:29092, data-service:50051,
   worklist-api:8000). Below, `os.environ.setdefault(...)` points
   `libs.common.settings` at `localhost` for exactly those instead of its
   container-network defaults (`mysql`, `redis`, `kafka:9092`,
   `data-service:50051`) -- but only when the env var isn't already set.
2. **Container-network mode.** Export `MYSQL_HOST=mysql`, `REDIS_HOST=redis`,
   `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`, `DATA_SERVICE_TARGET=data-service:50051`,
   `WORKLIST_API_BASE_URL=http://worklist-api:8000` (e.g. running pytest from
   a container attached to the compose network) before invoking pytest; the
   `setdefault()` calls below become no-ops.

See `tests/README.md` for the exact commands either way.
"""

from __future__ import annotations

import os

# These must run before `libs.common.settings` (or anything importing it) is
# ever imported, since `get_settings()` is `lru_cache`d for the process.
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
os.environ.setdefault("DATA_SERVICE_TARGET", "localhost:50051")
os.environ.setdefault("AS_OF_DATE", "2026-04-08")
# Not a libs.common.settings field -- worklist_api has no "target" setting of
# its own to reuse, so this is this test suite's own env var for where to
# reach the REST API.
_WORKLIST_API_BASE_URL = os.environ.setdefault("WORKLIST_API_BASE_URL", "http://localhost:8000")

import grpc  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from libs.common.grpc_client import data_service_stub  # noqa: E402
from libs.common.grpc_gen import dataservice_pb2 as pb  # noqa: E402
from libs.common.settings import get_settings  # noqa: E402

HEALTH_CHECK_TIMEOUT_SECONDS = 3.0


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return _WORKLIST_API_BASE_URL


@pytest.fixture(scope="session")
def live_stack(api_base_url: str) -> None:
    """Fails fast -- skips the whole dependent suite with a clear reason --
    if the stack's REST API isn't reachable, instead of every test hanging
    on its own default timeout. A single `GET /health` with a tight client
    timeout is enough: `docker-compose.yml` makes the Worklist API's own
    healthcheck depend on the Data Service being healthy first, so a
    reachable `/health` implies MySQL, Redis, Kafka and the Data Service all
    came up too.
    """
    try:
        resp = httpx.get(f"{api_base_url}/health", timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 -- anything here means "not reachable"
        pytest.skip(
            f"Live stack not reachable at {api_base_url}/health ({exc!r}). "
            "Bring it up first: `make up && make seed` (or "
            "`docker compose up -d` then `docker compose run --rm sync`). "
            "See tests/README.md."
        )


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def mysql_engine(settings):
    """Direct MySQL access for the checks the REST API can't express
    (raw `encounters` rows, `outbox`/`patient_eval_state`) or that need a
    full-table snapshot (the idempotency/failure tests' before/after diff of
    `tasks`). In the real architecture only the Data Service holds MySQL
    credentials (CLAUDE.md) -- this is test-only and read-mostly, and reuses
    the Data Service's own `sqlalchemy_url` via `libs.common.settings`
    rather than hardcoding a connection string here.
    """
    engine = sa.create_engine(settings.sqlalchemy_url, pool_pre_ping=True, pool_recycle=280)
    yield engine
    engine.dispose()


def _api_client(base_url: str, role: str, user_id: str = "integration-tests") -> httpx.Client:
    return httpx.Client(
        base_url=base_url, headers={"X-User-Role": role, "X-User-Id": user_id}, timeout=15.0
    )


@pytest.fixture(scope="session")
def scheduler_client(api_base_url, live_stack):
    with _api_client(api_base_url, "scheduler") as client:
        yield client


@pytest.fixture(scope="session")
def clinical_client(api_base_url, live_stack):
    with _api_client(api_base_url, "clinical") as client:
        yield client


@pytest.fixture(scope="session")
def admin_client(api_base_url, live_stack):
    with _api_client(api_base_url, "admin") as client:
        yield client


@pytest.fixture(scope="session")
def grpc_stub(settings, live_stack):
    """A real gRPC channel to the Data Service, for the checks the REST API
    doesn't expose at all (`SaveEvaluationResult`, `EnqueueAllPatients`).
    A quick `GetMeta` call fails the whole dependent suite fast, with a clear
    reason, if the gRPC target specifically isn't reachable even though the
    REST API's `/health` was (e.g. a container-network-mode env var typo).
    """
    stub = data_service_stub(settings.data_service_target)
    try:
        stub.GetMeta(pb.GetMetaRequest(), timeout=5)
    except grpc.RpcError as exc:
        pytest.skip(
            f"Data Service gRPC target {settings.data_service_target!r} not reachable: {exc}"
        )
    return stub
