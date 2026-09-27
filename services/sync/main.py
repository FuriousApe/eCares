"""Data Sync job entrypoint (`ROLE=sync`).

Runs once and exits (see the plan's local architecture): reads the four
source CSVs through a `SourceAdapter`, maps each row to the canonical field
names the Data Service expects, does a light shape check, and pushes
accepted rows to the Data Service over gRPC in fixed-size, retryable chunks.

All *real* validation (types, patient FK checks, natural-key dedup),
hashing, persistence and quarantine of individual rows happens in the Data
Service (CLAUDE.md decision #1) -- a row it rejects is a normal partial
success, not a sync failure. This job only fails its own run when something
in its own layer breaks: a CSV file is missing/unreadable, or the gRPC
channel never comes up.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import grpc

from libs.common.grpc_client import call_metadata, data_service_stub
from libs.common.grpc_gen import dataservice_pb2 as pb
from libs.common.logging import configure_logging
from libs.common.request_id import new_request_id, set_request_id
from libs.common.settings import get_settings
from services.sync.adapters import RESOURCE_ORDER, CsvAdapter, SourceAdapter
from services.sync.chunking import chunked
from services.sync.mappers import MalformedRowError, map_and_validate

logger = logging.getLogger("sync")

# 50-100 rows keeps each UpsertFactsRequest small (well under any gRPC
# message-size default) while keeping the chunk count, and therefore the
# retry surface, low for our biggest file (1159 encounter rows -> 12 chunks).
CHUNK_SIZE = 100

# A few retries with short exponential backoff: enough to ride out a
# transient blip (Data Service mid-restart, brief network hiccup) without
# turning a real outage into a multi-minute hang.
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 1.0  # 1s, 2s, 4s between attempts 1->2, 2->3, 3->4

RETRYABLE_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
}


def _upsert_chunk_with_retry(
    stub, run_id: str, resource_type: str, chunk_number: int, rows: list[dict[str, str]]
) -> pb.UpsertFactsResponse:
    """Sends one chunk, retrying transient gRPC failures with backoff.

    `chunk_number` never changes between attempts, so a retried chunk is a
    no-op on the Data Service side rather than a duplicate (CLAUDE.md #2).
    """
    request = pb.UpsertFactsRequest(
        run_id=run_id,
        resource_type=resource_type,
        chunk_number=chunk_number,
        rows=[pb.FactRow(fields=row) for row in rows],
    )
    delay = BACKOFF_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return stub.UpsertFacts(request, metadata=call_metadata())
        except grpc.RpcError as exc:
            code = exc.code() if hasattr(exc, "code") else None
            if code not in RETRYABLE_CODES or attempt == MAX_ATTEMPTS:
                raise
            logger.warning(
                "UpsertFacts %s chunk %d failed (%s), attempt %d/%d, retrying in %.0fs",
                resource_type,
                chunk_number,
                code,
                attempt,
                MAX_ATTEMPTS,
                delay,
            )
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable: loop always returns or raises")


def _sync_resource(
    stub, run_id: str, adapter: SourceAdapter, resource_type: str, chunk_size: int = CHUNK_SIZE
) -> dict[str, int]:
    """Reads, maps, validates and sends one resource's rows.

    Returns per-resource counts: `accepted` and `rejected` come from the Data
    Service's own response; `malformed` counts rows sync itself never sent
    (they never reach the Data Service, so they can't appear in its
    `sync_quarantine` -- see the mappers module docstring).
    """
    mapped_rows: list[dict[str, str]] = []
    malformed = 0
    for _, raw_row in adapter.rows(resource_type):
        try:
            mapped_rows.append(map_and_validate(resource_type, raw_row))
        except MalformedRowError as exc:
            malformed += 1
            logger.warning("skipping malformed %s row: %s", resource_type, exc)

    accepted = 0
    rejected = 0
    for chunk_number, chunk in enumerate(chunked(mapped_rows, chunk_size)):
        response = _upsert_chunk_with_retry(stub, run_id, resource_type, chunk_number, chunk)
        accepted += response.accepted_count
        rejected += len(response.rejected)
        for row in response.rejected:
            logger.info(
                "Data Service rejected a %s row (%s): %s", resource_type, row.reason, dict(row.raw)
            )

    return {"accepted": accepted, "rejected": rejected, "malformed": malformed}


@dataclass
class SyncRunResult:
    """Everything a caller of `run_sync` might need — the CLI entrypoint only
    cares about `exit_code`, but `/admin/sync` (services/worklist_api) also
    wants the run id and which patients changed, so this carries both rather
    than making that caller re-derive them with extra RPCs."""

    exit_code: int
    run_id: str = ""
    status: str = "failed"
    changed_patient_ids: list[str] = field(default_factory=list)
    counts_json: str = ""


def run_sync(adapter: SourceAdapter, stub, chunk_size: int = CHUNK_SIZE) -> SyncRunResult:
    """Runs one full sync end to end."""
    try:
        start_response = stub.StartSyncRun(
            pb.StartSyncRunRequest(source="csv"), metadata=call_metadata()
        )
        run_id = start_response.run_id
    except grpc.RpcError:
        logger.exception("could not start a sync run")
        return SyncRunResult(exit_code=1)
    logger.info("started sync run %s", run_id)

    summary: dict[str, dict[str, int]] = {}
    status = "completed"
    for resource_type in RESOURCE_ORDER:
        try:
            summary[resource_type] = _sync_resource(
                stub, run_id, adapter, resource_type, chunk_size
            )
        except Exception:
            logger.exception(
                "sync run %s failed reading/sending %s -- stopping this run", run_id, resource_type
            )
            status = "failed"
            break
        counts = summary[resource_type]
        logger.info(
            "%s: accepted=%d rejected=%d malformed=%d",
            resource_type,
            counts["accepted"],
            counts["rejected"],
            counts["malformed"],
        )

    try:
        complete = stub.CompleteSyncRun(
            pb.CompleteSyncRunRequest(run_id=run_id, status=status), metadata=call_metadata()
        )
    except grpc.RpcError:
        logger.exception("could not complete sync run %s", run_id)
        return SyncRunResult(exit_code=1, run_id=run_id, status=status)

    changed_ids = list(complete.changed_patient_ids)
    _log_summary(run_id, status, summary, changed_ids, complete.run.counts_json)
    return SyncRunResult(
        exit_code=0 if status == "completed" else 1,
        run_id=run_id,
        status=status,
        changed_patient_ids=changed_ids,
        counts_json=complete.run.counts_json,
    )


def _log_summary(
    run_id: str,
    status: str,
    summary: dict[str, dict[str, int]],
    changed_patient_ids: list[str],
    counts_json: str,
) -> None:
    lines = [f"sync run {run_id}: {status}"]
    for resource_type, counts in summary.items():
        lines.append(
            f"  {resource_type:<11} accepted={counts['accepted']:<5} "
            f"rejected={counts['rejected']:<4} malformed_before_send={counts['malformed']}"
        )
    lines.append(f"  changed_patients={len(changed_patient_ids)}")
    lines.append(f"  counts_json={counts_json}")
    logger.info("\n".join(lines))


def main() -> None:
    settings = get_settings()
    configure_logging("sync")
    set_request_id(new_request_id())

    # No dedicated setting in libs/common/settings.py for this (out of
    # scope to add one); the Compose file mounts the CSVs at ./data, which
    # is "data" relative to the container's /app cwd, so that's the default.
    data_dir = Path(os.environ.get("SYNC_DATA_DIR", "data"))
    adapter = CsvAdapter(data_dir)
    stub = data_service_stub(settings.data_service_target)

    result = run_sync(adapter, stub)
    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
