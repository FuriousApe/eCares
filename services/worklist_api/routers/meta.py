"""GET /meta — as-of date, last sync time, task counts."""

from __future__ import annotations

from fastapi import APIRouter

from libs.common.grpc_gen import dataservice_pb2 as pb
from services.worklist_api.deps import CallerDep, StubDep
from services.worklist_api.grpc_calls import call
from services.worklist_api.schemas import MetaOut

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaOut)
def get_meta(caller: CallerDep, stub: StubDep) -> MetaOut:
    resp = call(stub.GetMeta, pb.GetMetaRequest())
    return MetaOut(
        as_of_date=resp.as_of_date,
        last_sync_finished_at=(
            resp.last_sync_finished_at if resp.HasField("last_sync_finished_at") else None
        ),
        task_counts_by_status=dict(resp.task_counts_by_status),
    )
