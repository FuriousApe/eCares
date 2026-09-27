"""Admin-only ops endpoints: /admin/sync, /admin/evaluate, /admin/sync-runs.

See ASSUMPTIONS.md for what `/admin/evaluate`'s single-patient case does and
does not do against the current proto contract (no single-patient enqueue
RPC exists yet).

`/admin/sync` used to only record an empty ledger entry (no proto RPC runs
an end-to-end CSV load). Per CLAUDE.md decision #15, it now calls
`services/sync`'s own `run_sync()` in-process instead of duplicating its
CSV/mapping/chunking logic — both services ship in the same monorepo image,
so the function is just importable. `run_sync` is synchronous and blocks
for the duration of a full load (a few seconds for the seed CSVs); FastAPI
runs a plain `def` endpoint in a thread pool, so this doesn't block the
event loop.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query

from libs.common import errors
from libs.common.grpc_gen import dataservice_pb2 as pb
from libs.common.settings import get_settings
from services.sync.adapters import CsvAdapter
from services.sync.main import run_sync
from services.worklist_api import mapping
from services.worklist_api.deps import AdminDep, StubDep
from services.worklist_api.grpc_calls import call
from services.worklist_api.schemas import (
    EvaluateTriggerOut,
    ListSyncRunsOut,
    SyncTriggerOut,
)

router = APIRouter(tags=["admin"])


@router.post("/admin/sync", response_model=SyncTriggerOut)
def trigger_sync(caller: AdminDep, stub: StubDep) -> SyncTriggerOut:
    # Same CSV directory convention services/sync/main.py uses: SYNC_DATA_DIR
    # env var, defaulting to "data" relative to the container's /app cwd.
    data_dir = Path(os.environ.get("SYNC_DATA_DIR", "data"))
    result = run_sync(CsvAdapter(data_dir), stub)
    if result.exit_code != 0:
        raise errors.AppError(
            "sync_failed",
            f"The sync run ({result.run_id or 'unstarted'}) failed — see worklist-api logs.",
            502,
        )

    # run_sync() already ran CompleteSyncRun; ListSyncRuns gets us the same
    # row back as a proto SyncRun so the response reuses the one mapping
    # function every other run-ledger endpoint uses, instead of duplicating
    # SyncRunOut construction here.
    runs = call(stub.ListSyncRuns, pb.ListSyncRunsRequest(limit=1))
    latest = next((r for r in runs.items if r.run_id == result.run_id), None) or runs.items[0]
    return SyncTriggerOut(
        run=mapping.sync_run_out(latest), changed_patient_ids=result.changed_patient_ids
    )


@router.post("/admin/evaluate", response_model=EvaluateTriggerOut)
def trigger_evaluate(
    caller: AdminDep,
    stub: StubDep,
    patient_id: str | None = None,
    all: Annotated[bool, Query()] = False,  # matches the plan's "all=true" query param
) -> EvaluateTriggerOut:
    if bool(patient_id) == bool(all):
        raise errors.ValidationError("Provide exactly one of patient_id or all=true")

    if all:
        resp = call(stub.EnqueueAllPatients, pb.EnqueueAllPatientsRequest())
        return EvaluateTriggerOut(enqueued_count=resp.enqueued_count, scope="all")

    # No single-patient enqueue RPC exists on the proto (see ASSUMPTIONS.md):
    # the closest available primitive is EnqueueDuePatients, which enqueues
    # every currently-due patient, not just this one.
    as_of = get_settings().effective_as_of_date().isoformat()
    resp = call(stub.EnqueueDuePatients, pb.EnqueueDuePatientsRequest(as_of_date=as_of))
    return EvaluateTriggerOut(
        enqueued_count=resp.enqueued_count,
        scope="patient",
        note=(
            f"No single-patient enqueue RPC exists yet; triggered EnqueueDuePatients "
            f"(all currently-due patients), which includes {patient_id} if due. "
            "See services/worklist_api/ASSUMPTIONS.md."
        ),
    )


@router.get("/admin/sync-runs", response_model=ListSyncRunsOut)
def list_sync_runs(
    caller: AdminDep,
    stub: StubDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ListSyncRunsOut:
    resp = call(stub.ListSyncRuns, pb.ListSyncRunsRequest(limit=limit))
    return ListSyncRunsOut(items=[mapping.sync_run_out(r) for r in resp.items])
