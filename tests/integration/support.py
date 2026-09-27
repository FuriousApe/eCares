"""Shared, non-fixture helpers for the live-stack integration suite: polling
with a real timeout (never sleep-and-hope), MySQL task snapshots, shelling
out to `tests/oracle.py` for a second opinion at a different as-of date, and
the Docker Compose mechanics behind the time-travel test.

Nothing here is a pytest fixture on purpose -- fixtures that need these live
in `tests/conftest.py` / `tests/integration/conftest.py`, so this module can
be imported and unit-tested (or reasoned about) without a live stack.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import httpx
import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AS_OF = date(2026, 4, 8)

# Every container whose behavior actually reads AS_OF_DATE. Restarted
# together for the time-travel test so the Worklist API's own as-of-date
# reads (days_overdue fallback, /admin/evaluate's EnqueueDuePatients call)
# agree with what the engine/data-service just applied, not the old date.
AS_OF_SERVICES = ("data-service", "engine", "scheduler", "worklist-api")


class WaitTimeout(RuntimeError):
    """Raised by `wait_until` -- distinct from a bare AssertionError so a
    failed poll reads as "the stack never got there" rather than "a value
    was wrong", which is a different bug to go chase."""


def wait_until(predicate: Callable[[], bool], timeout: float, interval: float, desc: str) -> None:
    """Poll `predicate` until truthy, or raise `WaitTimeout` with a clear
    message. Every wall-clock wait in this suite (Kafka propagation, a
    container coming back healthy, the engine draining a backlog) goes
    through this instead of a fixed `sleep()` guess.
    """
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception as exc:  # noqa: BLE001 -- keep polling, surface the last one
            last_exc = exc
        time.sleep(interval)
    suffix = f" (last error while polling: {last_exc!r})" if last_exc else ""
    raise WaitTimeout(f"Timed out after {timeout}s waiting for: {desc}{suffix}")


# ---------------------------------------------------------------------------
# Direct MySQL reads
# ---------------------------------------------------------------------------


def snapshot_tasks(engine: sa.Engine) -> list[tuple[int, str, int]]:
    """(task_id, status, version) for every row, sorted by task_id -- the
    exact shape the idempotency/failure tests diff before vs. after."""
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT task_id, status, version FROM tasks ORDER BY task_id"))
        return [(r.task_id, r.status, r.version) for r in rows]


def tasks_fingerprint(engine: sa.Engine) -> tuple[int, object]:
    """Cheap "has anything changed" signal for polling: row count plus the
    latest `updated_at`. Good enough to detect the engine still churning
    without re-reading the whole table on every poll tick."""
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT COUNT(*) AS n, MAX(updated_at) AS latest FROM tasks")
        ).one()
        return (row.n, row.latest)


def wait_for_tasks_to_settle(
    engine: sa.Engine, timeout: float = 120.0, interval: float = 2.0, stable_rounds: int = 3
) -> None:
    """Waits until the `tasks` table's fingerprint stops changing for
    `stable_rounds` consecutive polls. The engine consumes `patient.changed`
    asynchronously over Kafka, so there is no single RPC response that means
    "the bulk evaluation is done" -- this is the poll every behavior test
    that triggers a (re-)evaluation uses instead of a fixed sleep.
    """
    seen: list[tuple[int, object]] = []

    def _stable() -> bool:
        seen.append(tasks_fingerprint(engine))
        if len(seen) < stable_rounds:
            return False
        return len(set(seen[-stable_rounds:])) == 1

    wait_until(_stable, timeout=timeout, interval=interval, desc="tasks table to stop changing")


def count_outbox_rows(engine: sa.Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT COUNT(*) FROM outbox")).scalar_one()


def count_open_tasks_for_key(
    engine: sa.Engine, patient_id: str, program_id: str, specialty: str
) -> int:
    with engine.connect() as conn:
        return conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM tasks WHERE patient_id=:p AND program_id=:pr "
                "AND specialty=:s AND status IN ('open','in_progress')"
            ),
            {"p": patient_id, "pr": program_id, "s": specialty},
        ).scalar_one()


# ---------------------------------------------------------------------------
# The oracle, as a second opinion from a separate process
# ---------------------------------------------------------------------------


def run_oracle(as_of: date, python_executable: str | None = None) -> dict:
    """Shells out to `tests/oracle.py --as-of <date> --json` and parses its
    output. A genuinely separate process (not an in-process import) so the
    comparison stays honest: this suite's expectation for a moved as-of date
    comes from the same independent script `make verify` runs, not from
    re-deriving numbers inline in a test file.
    """
    python_executable = python_executable or sys.executable
    result = subprocess.run(
        [
            python_executable,
            str(REPO_ROOT / "tests" / "oracle.py"),
            "--as-of",
            as_of.isoformat(),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tests/oracle.py --as-of {as_of} failed:\n{result.stderr}")
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Docker Compose mechanics for the time-travel test
# ---------------------------------------------------------------------------


def compose(*args: str, timeout: float = 180.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _override_yaml(as_of_iso: str) -> str:
    services = "\n".join(
        f'  {name}:\n    environment:\n      AS_OF_DATE: "{as_of_iso}"' for name in AS_OF_SERVICES
    )
    return f"services:\n{services}\n"


def _service_running(name: str) -> bool:
    """Best-effort: `docker compose ps --format json` is compose v2 syntax
    (one JSON object per line). Falls back to a substring check on plain
    text output for an older/different compose build rather than raising --
    this is only used to decide when it's safe to proceed, not to assert
    correctness, so a false negative just means "wait a bit longer"."""
    result = compose("ps", name, "--format", "json", timeout=15)
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        for line in result.stdout.strip().splitlines():
            obj = json.loads(line)
            if obj.get("State") == "running":
                return True
        return False
    except json.JSONDecodeError:
        return "running" in result.stdout.lower()


def _wait_for_stack_healthy(api_base_url: str, timeout: float = 150.0) -> None:
    def _ready() -> bool:
        try:
            resp = httpx.get(f"{api_base_url}/health", timeout=3.0)
            api_ok = resp.status_code == 200
        except httpx.HTTPError:
            api_ok = False
        return api_ok and _service_running("engine") and _service_running("scheduler")

    wait_until(
        _ready,
        timeout=timeout,
        interval=3.0,
        desc="data-service/worklist-api/engine/scheduler healthy after an AS_OF_DATE override",
    )


@contextmanager
def as_of_date_override(new_as_of: date, api_base_url: str):
    """Restarts data-service/engine/scheduler/worklist-api with a different
    `AS_OF_DATE`, via a throwaway Compose override file (Compose has no `-e`
    flag on `up`), and restores 2026-04-08 on the way out even if the test
    body raises.

    See tests/ASSUMPTIONS.md for the full mechanism, why this approach was
    chosen over the alternatives the task sketch mentioned, and its known
    limitations (no live stack was available to exercise this for real
    while writing it -- see the honesty note there).
    """
    override_path = REPO_ROOT / "docker-compose.override.integration-test.yml"
    try:
        override_path.write_text(_override_yaml(new_as_of.isoformat()))
        result = compose(
            "-f",
            "docker-compose.yml",
            "-f",
            override_path.name,
            "up",
            "-d",
            "--force-recreate",
            *AS_OF_SERVICES,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker compose up --force-recreate failed:\n{result.stderr}")
        _wait_for_stack_healthy(api_base_url)
        yield
    finally:
        try:
            override_path.write_text(_override_yaml(DEFAULT_AS_OF.isoformat()))
            compose(
                "-f",
                "docker-compose.yml",
                "-f",
                override_path.name,
                "up",
                "-d",
                "--force-recreate",
                *AS_OF_SERVICES,
            )
            _wait_for_stack_healthy(api_base_url)
        finally:
            override_path.unlink(missing_ok=True)
