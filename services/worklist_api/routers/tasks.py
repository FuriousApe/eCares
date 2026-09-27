"""GET /tasks, GET /tasks/{task_id}, and the four task mutations.

Role visibility always goes into the gRPC request's `RoleFilter` (never
filtered after the fact here). Mutation error mapping (stale version -> 409,
illegal transition -> 422, hidden task -> 404) happens once, in
`grpc_calls.call`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from libs.common.grpc_gen import dataservice_pb2 as pb
from libs.common.settings import get_settings
from services.worklist_api import mapping
from services.worklist_api.deps import CallerDep, StubDep
from services.worklist_api.grpc_calls import call
from services.worklist_api.schemas import (
    ClaimTaskBody,
    CompleteTaskBody,
    DeclineTaskBody,
    ListTasksResponseOut,
    SnoozeTaskBody,
    TaskDetailOut,
    TaskOut,
)

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=ListTasksResponseOut)
def list_tasks(
    caller: CallerDep,
    stub: StubDep,
    specialty: str | None = None,
    task_type: str | None = None,
    status: Annotated[list[str] | None, Query()] = None,
    program: str | None = None,
    tier: str | None = None,
    assigned_to: str | None = None,
    overdue: bool | None = None,
    include_snoozed: bool = False,
    sort: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> ListTasksResponseOut:
    req = pb.ListTasksRequest(
        role_filter=mapping.role_filter(caller),
        status=status or ["open", "in_progress"],
        include_snoozed=include_snoozed,
        limit=limit,
    )
    if specialty:
        req.specialty = specialty
    if task_type:
        req.task_type = task_type
    if program:
        req.program = program
    if tier:
        req.tier = tier
    if assigned_to:
        req.assigned_to = assigned_to
    if overdue is not None:
        req.overdue = overdue
    if sort:
        req.sort = sort
    if cursor:
        req.cursor = cursor

    resp = call(stub.ListTasks, req)
    as_of = get_settings().effective_as_of_date()
    return ListTasksResponseOut(
        items=[mapping.task_out(t, as_of) for t in resp.items],
        next_cursor=resp.next_cursor if resp.HasField("next_cursor") else None,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetailOut)
def get_task(task_id: int, caller: CallerDep, stub: StubDep) -> TaskDetailOut:
    req = pb.GetTaskRequest(task_id=task_id, role_filter=mapping.role_filter(caller))
    resp = call(stub.GetTask, req)
    as_of = get_settings().effective_as_of_date()
    return TaskDetailOut(
        task=mapping.task_out(resp.task, as_of),
        history=[mapping.audit_entry_out(a) for a in resp.history],
    )


@router.post("/tasks/{task_id}/claim", response_model=TaskOut)
def claim_task(
    task_id: int, body: ClaimTaskBody, caller: CallerDep, stub: StubDep
) -> TaskOut:
    req = pb.ClaimTaskRequest(
        task_id=task_id, version=body.version, role_filter=mapping.role_filter(caller)
    )
    resp = call(stub.ClaimTask, req)
    return mapping.task_out(resp.task, get_settings().effective_as_of_date())


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: int, body: CompleteTaskBody, caller: CallerDep, stub: StubDep
) -> TaskOut:
    req = pb.CompleteTaskRequest(
        task_id=task_id,
        version=body.version,
        resolution=body.resolution,
        role_filter=mapping.role_filter(caller),
    )
    if body.note:
        req.note = body.note
    resp = call(stub.CompleteTask, req)
    return mapping.task_out(resp.task, get_settings().effective_as_of_date())


@router.post("/tasks/{task_id}/decline", response_model=TaskOut)
def decline_task(
    task_id: int, body: DeclineTaskBody, caller: CallerDep, stub: StubDep
) -> TaskOut:
    req = pb.DeclineTaskRequest(
        task_id=task_id,
        version=body.version,
        reason=body.reason,
        snooze_days=body.snooze_days,
        role_filter=mapping.role_filter(caller),
    )
    resp = call(stub.DeclineTask, req)
    return mapping.task_out(resp.task, get_settings().effective_as_of_date())


@router.post("/tasks/{task_id}/snooze", response_model=TaskOut)
def snooze_task(
    task_id: int, body: SnoozeTaskBody, caller: CallerDep, stub: StubDep
) -> TaskOut:
    req = pb.SnoozeTaskRequest(
        task_id=task_id,
        version=body.version,
        until=body.until.isoformat(),
        reason=body.reason,
        role_filter=mapping.role_filter(caller),
    )
    resp = call(stub.SnoozeTask, req)
    return mapping.task_out(resp.task, get_settings().effective_as_of_date())
