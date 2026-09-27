"""GET /programs — active program definitions."""

from __future__ import annotations

from fastapi import APIRouter

from libs.common.grpc_gen import dataservice_pb2 as pb
from services.worklist_api import mapping
from services.worklist_api.deps import CallerDep, StubDep
from services.worklist_api.grpc_calls import call
from services.worklist_api.schemas import ListProgramsResponseOut

router = APIRouter(tags=["programs"])


@router.get("/programs", response_model=ListProgramsResponseOut)
def list_programs(caller: CallerDep, stub: StubDep) -> ListProgramsResponseOut:
    resp = call(stub.ListPrograms, pb.ListProgramsRequest())
    return ListProgramsResponseOut(items=[mapping.program_out(p) for p in resp.items])
