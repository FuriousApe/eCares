"""The gRPC servicer: thin adapter between protobuf messages and the
repository functions, which work in plain dicts/dates so they stay testable
without protobuf or a live server.

gRPC error convention (see ASSUMPTIONS.md for the full table): every
`AppError` the repositories raise is translated to a `grpc.StatusCode` and
the error's machine-readable `code` (from `libs.common.errors`) is placed in
the trailing metadata under the key `"code"`, so callers such as the
Worklist API can map it to the exact REST status the plan specifies without
string-matching the message.
"""

from __future__ import annotations

from datetime import date, datetime

import grpc

from libs.common.errors import AppError
from libs.common.grpc_gen import dataservice_pb2
from libs.common.request_id import GRPC_METADATA_KEY, new_request_id
from libs.common.settings import get_settings
from services.data_service.audit import write_audit
from services.data_service.cache import (
    bump_generation,
    cache_get_json,
    cache_set_json,
    get_active_programs,
    set_active_programs,
    worklist_cache_key,
)
from services.data_service.db import session_scope
from services.data_service.repositories import evaluation, reads, sync, tasks

_CODE_TO_GRPC_STATUS = {
    "not_found": grpc.StatusCode.NOT_FOUND,
    "version_conflict": grpc.StatusCode.ABORTED,
    "illegal_transition": grpc.StatusCode.FAILED_PRECONDITION,
    "validation_error": grpc.StatusCode.INVALID_ARGUMENT,
    "forbidden": grpc.StatusCode.PERMISSION_DENIED,
}


def _request_id(context: grpc.ServicerContext) -> str:
    for key, value in context.invocation_metadata() or ():
        if key == GRPC_METADATA_KEY:
            return value
    return new_request_id()


def _abort(context: grpc.ServicerContext, err: AppError) -> None:
    context.set_trailing_metadata((("code", err.code),))
    context.abort(_CODE_TO_GRPC_STATUS.get(err.code, grpc.StatusCode.INTERNAL), err.message)


def _as_of_date() -> date:
    return get_settings().effective_as_of_date()


# --- dict -> proto ----------------------------------------------------------


def _patient_proto(d: dict | None) -> dataservice_pb2.Patient | None:
    if d is None:
        return None
    fields = {k: v for k, v in d.items() if k != "pcp_provider_name"}
    proto = dataservice_pb2.Patient(**fields)
    if d.get("pcp_provider_name"):
        proto.pcp_provider_name = d["pcp_provider_name"]
    return proto


def _enrollment_proto(d: dict) -> dataservice_pb2.Enrollment:
    return dataservice_pb2.Enrollment(
        program_id=d["program_id"], program_version=d["program_version"], tier=d["tier"], evaluated_at=d["evaluated_at"]
    )


def _need_proto(d: dict) -> dataservice_pb2.Need:
    proto = dataservice_pb2.Need(
        program_id=d["program_id"],
        specialty=d["specialty"],
        cadence_days=d["cadence_days"],
        has_upcoming=d["has_upcoming"],
    )
    if d.get("last_visit_date"):
        proto.last_visit_date = d["last_visit_date"]
    if d.get("due_date"):
        proto.due_date = d["due_date"]
    return proto


def _task_proto(d: dict) -> dataservice_pb2.Task:
    proto = dataservice_pb2.Task(
        task_id=d["task_id"],
        patient_id=d["patient_id"],
        program_id=d["program_id"],
        tier=d["tier"],
        specialty=d["specialty"],
        task_type=d["task_type"],
        status=d["status"],
        program_version=d["program_version"],
        version=d["version"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )
    if d.get("due_date"):
        proto.due_date = d["due_date"]
    if d.get("days_overdue") is not None:
        proto.days_overdue = d["days_overdue"]
    if d.get("snooze_until"):
        proto.snooze_until = d["snooze_until"]
    if d.get("resolution"):
        proto.resolution = d["resolution"]
    if d.get("assigned_to"):
        proto.assigned_to = d["assigned_to"]
    if d.get("patient"):
        proto.patient.CopyFrom(_patient_proto(d["patient"]))
    return proto


def _audit_proto(d: dict) -> dataservice_pb2.AuditEntry:
    proto = dataservice_pb2.AuditEntry(
        event_id=d["event_id"],
        occurred_at=d["occurred_at"],
        actor=d["actor"],
        action=d["action"],
        entity=d["entity"],
        before_json=d["before_json"],
        after_json=d["after_json"],
        request_id=d["request_id"],
        result=d["result"],
    )
    if d.get("patient_id"):
        proto.patient_id = d["patient_id"]
    return proto


def _program_proto(d: dict) -> dataservice_pb2.Program:
    return dataservice_pb2.Program(
        program_id=d["program_id"], version=d["version"], definition_json=d["definition_json"], active=d["active"]
    )


def _sync_run_proto(d: dict) -> dataservice_pb2.SyncRun:
    proto = dataservice_pb2.SyncRun(
        run_id=d["run_id"],
        status=d["status"],
        started_at=d["started_at"],
        counts_json=d["counts_json"],
        watermarks_json=d["watermarks_json"],
    )
    if d.get("finished_at"):
        proto.finished_at = d["finished_at"]
    return proto


class DataServiceServicer:
    """Registered with `add_DataServiceServicer_to_server` in main.py."""

    # --- interactive read ---------------------------------------------------

    def GetMeta(self, request, context):
        with session_scope() as session:
            meta = reads.get_meta(session, _as_of_date())
        resp = dataservice_pb2.GetMetaResponse(
            as_of_date=meta["as_of_date"], task_counts_by_status=meta["task_counts_by_status"]
        )
        if meta.get("last_sync_finished_at"):
            resp.last_sync_finished_at = meta["last_sync_finished_at"]
        return resp

    def ListPatients(self, request, context):
        role = request.role_filter
        filters = _request_to_filter_dict(request)
        cache_key = worklist_cache_key(_role_cache_key(role), filters, request.cursor or None)
        try:
            with session_scope() as session:
                items, next_cursor = _cached_page(
                    cache_key,
                    lambda: reads.list_patients(
                        session,
                        allowed_task_types=list(role.allowed_task_types),
                        specialty=request.specialty or None,
                        task_type=request.task_type or None,
                        status=request.status or None,
                        program=request.program or None,
                        tier=request.tier or None,
                        q_text=request.q or None,
                        limit=request.limit,
                        cursor=request.cursor or None,
                        as_of_date=_as_of_date(),
                    ),
                )
                write_audit(
                    session,
                    actor=role.user_id,
                    action="list_patients",
                    entity="patient",
                    patient_id=None,
                    before=None,
                    after={"filters": filters, "row_count": len(items)},
                    request_id=_request_id(context),
                )
        except AppError as err:
            return _abort(context, err)
        resp = dataservice_pb2.ListPatientsResponse(
            items=[
                dataservice_pb2.PatientWithContext(
                    patient=_patient_proto(i["patient"]),
                    enrollments=[_enrollment_proto(e) for e in i["enrollments"]],
                    visible_tasks=[_task_proto(t) for t in i["visible_tasks"]],
                )
                for i in items
            ]
        )
        if next_cursor:
            resp.next_cursor = next_cursor
        return resp

    def GetPatient(self, request, context):
        role = request.role_filter
        try:
            with session_scope() as session:
                result = reads.get_patient(session, request.patient_id, list(role.allowed_task_types), _as_of_date())
                write_audit(
                    session,
                    actor=role.user_id,
                    action="get_patient",
                    entity="patient",
                    patient_id=request.patient_id,
                    before=None,
                    after={"note": "patient detail read"},
                    request_id=_request_id(context),
                )
        except AppError as err:
            return _abort(context, err)
        return dataservice_pb2.GetPatientResponse(
            patient=_patient_proto(result["patient"]),
            enrollments=[_enrollment_proto(e) for e in result["enrollments"]],
            needs=[_need_proto(n) for n in result["needs"]],
            visible_tasks=[_task_proto(t) for t in result["visible_tasks"]],
        )

    def ListTasks(self, request, context):
        role = request.role_filter
        filters = _request_to_filter_dict(request)
        cache_key = worklist_cache_key(_role_cache_key(role), filters, request.cursor or None)
        try:
            with session_scope() as session:
                items, next_cursor = _cached_page(
                    cache_key,
                    lambda: reads.list_tasks(
                        session,
                        allowed_task_types=list(role.allowed_task_types),
                        specialty=request.specialty or None,
                        task_type=request.task_type or None,
                        statuses=list(request.status),
                        program=request.program or None,
                        tier=request.tier or None,
                        assigned_to=request.assigned_to or None,
                        overdue=request.overdue if request.HasField("overdue") else None,
                        include_snoozed=request.include_snoozed,
                        limit=request.limit,
                        cursor=request.cursor or None,
                        as_of_date=_as_of_date(),
                    ),
                )
                write_audit(
                    session,
                    actor=role.user_id,
                    action="list_tasks",
                    entity="task",
                    patient_id=None,
                    before=None,
                    after={"filters": filters, "row_count": len(items)},
                    request_id=_request_id(context),
                )
        except AppError as err:
            return _abort(context, err)
        resp = dataservice_pb2.ListTasksResponse(items=[_task_proto(t) for t in items])
        if next_cursor:
            resp.next_cursor = next_cursor
        return resp

    def GetTask(self, request, context):
        role = request.role_filter
        try:
            with session_scope() as session:
                result = reads.get_task(session, request.task_id, list(role.allowed_task_types), _as_of_date())
        except AppError as err:
            return _abort(context, err)
        return dataservice_pb2.GetTaskResponse(
            task=_task_proto(result["task"]), history=[_audit_proto(h) for h in result["history"]]
        )

    def ListPrograms(self, request, context):
        programs = get_active_programs()
        if programs is None:
            with session_scope() as session:
                programs = reads.list_programs(session)
            set_active_programs(programs)
        return dataservice_pb2.ListProgramsResponse(items=[_program_proto(p) for p in programs])

    # --- interactive write ---------------------------------------------------

    def ClaimTask(self, request, context):
        try:
            with session_scope() as session:
                result = tasks.claim_task(
                    session,
                    task_id=request.task_id,
                    version=request.version,
                    role_filter=request.role_filter,
                    request_id=_request_id(context),
                    as_of_date=_as_of_date(),
                )
        except AppError as err:
            return _abort(context, err)
        bump_generation()
        return dataservice_pb2.TaskResponse(task=_task_proto(result))

    def CompleteTask(self, request, context):
        try:
            with session_scope() as session:
                result = tasks.complete_task(
                    session,
                    task_id=request.task_id,
                    version=request.version,
                    resolution=request.resolution,
                    note=request.note or None,
                    role_filter=request.role_filter,
                    request_id=_request_id(context),
                    as_of_date=_as_of_date(),
                )
        except AppError as err:
            return _abort(context, err)
        bump_generation()
        return dataservice_pb2.TaskResponse(task=_task_proto(result))

    def DeclineTask(self, request, context):
        try:
            with session_scope() as session:
                result = tasks.decline_task(
                    session,
                    task_id=request.task_id,
                    version=request.version,
                    reason=request.reason,
                    snooze_days=request.snooze_days,
                    role_filter=request.role_filter,
                    request_id=_request_id(context),
                    as_of_date=_as_of_date(),
                    default_snooze_days=get_settings().default_decline_snooze_days,
                )
        except AppError as err:
            return _abort(context, err)
        bump_generation()
        return dataservice_pb2.TaskResponse(task=_task_proto(result))

    def SnoozeTask(self, request, context):
        try:
            with session_scope() as session:
                result = tasks.snooze_task(
                    session,
                    task_id=request.task_id,
                    version=request.version,
                    until=date.fromisoformat(request.until),
                    reason=request.reason,
                    role_filter=request.role_filter,
                    request_id=_request_id(context),
                    as_of_date=_as_of_date(),
                )
        except AppError as err:
            return _abort(context, err)
        bump_generation()
        return dataservice_pb2.TaskResponse(task=_task_proto(result))

    # --- bulk: sync -----------------------------------------------------------

    def StartSyncRun(self, request, context):
        with session_scope() as session:
            run_id = sync.start_sync_run(session, request.source)
        return dataservice_pb2.StartSyncRunResponse(run_id=run_id)

    def UpsertFacts(self, request, context):
        rows = [dict(r.fields) for r in request.rows]
        try:
            with session_scope() as session:
                accepted_count, rejected = sync.upsert_facts(
                    session,
                    run_id=request.run_id,
                    resource_type=request.resource_type,
                    chunk_number=request.chunk_number,
                    rows=rows,
                )
        except AppError as err:
            return _abort(context, err)
        return dataservice_pb2.UpsertFactsResponse(
            accepted_count=accepted_count,
            rejected=[dataservice_pb2.RejectedRow(raw=r["raw"], reason=r["reason"]) for r in rejected],
        )

    def CompleteSyncRun(self, request, context):
        try:
            with session_scope() as session:
                result = sync.complete_sync_run(session, run_id=request.run_id, status=request.status)
        except AppError as err:
            return _abort(context, err)
        return dataservice_pb2.CompleteSyncRunResponse(
            run=_sync_run_proto(result), changed_patient_ids=result["changed_patient_ids"]
        )

    def ListSyncRuns(self, request, context):
        with session_scope() as session:
            runs = reads.list_sync_runs(session, request.limit)
        return dataservice_pb2.ListSyncRunsResponse(items=[_sync_run_proto(r) for r in runs])

    def UpsertPrograms(self, request, context):
        programs = [
            {
                "program_id": p.program_id,
                "version": p.version,
                "definition_json": p.definition_json,
                "active": p.active,
            }
            for p in request.programs
        ]
        with session_scope() as session:
            count = evaluation.upsert_programs(session, programs)
        return dataservice_pb2.UpsertProgramsResponse(upserted_count=count)

    # --- bulk: engine -----------------------------------------------------------

    def GetPatientSnapshot(self, request, context):
        as_of = date.fromisoformat(request.as_of_date) if request.as_of_date else _as_of_date()
        try:
            with session_scope() as session:
                snap = evaluation.get_patient_snapshot(session, request.patient_id, as_of)
        except AppError as err:
            return _abort(context, err)
        return dataservice_pb2.GetPatientSnapshotResponse(
            patient=_patient_proto(snap["patient"]),
            diagnoses=[dataservice_pb2.DiagnosisFact(**d) for d in snap["diagnoses"]],
            labs=[dataservice_pb2.LabFact(**lab) for lab in snap["labs"]],
            encounters=[dataservice_pb2.EncounterFact(**e) for e in snap["encounters"]],
            snapshot_hash=snap["snapshot_hash"],
        )

    def SaveEvaluationResult(self, request, context):
        program_results = [_program_result_from_proto(p) for p in request.program_results]
        # The engine's own `next_eval_at`: earliest of its computed trigger
        # dates, ignoring snoozes entirely (empty string when it has none —
        # not a sentinel date). This service folds in any active decline
        # snooze itself; see evaluation.save_evaluation_result.
        next_eval_at_candidate = date.fromisoformat(request.next_eval_at) if request.next_eval_at else None
        try:
            with session_scope() as session:
                result = evaluation.save_evaluation_result(
                    session,
                    patient_id=request.patient_id,
                    idempotency_key=request.idempotency_key,
                    program_results=program_results,
                    evaluated_at=datetime.fromisoformat(request.evaluated_at),
                    next_eval_at_candidate=next_eval_at_candidate,
                    request_id=_request_id(context),
                    as_of_date=_as_of_date(),
                )
        except AppError as err:
            return _abort(context, err)
        if result["applied"] and (result["tasks_created"] or result["tasks_closed"]):
            bump_generation()
        return dataservice_pb2.SaveEvaluationResultResponse(
            applied=result["applied"], tasks_created=result["tasks_created"], tasks_closed=result["tasks_closed"]
        )

    def EnqueueDuePatients(self, request, context):
        as_of = date.fromisoformat(request.as_of_date) if request.as_of_date else _as_of_date()
        with session_scope() as session:
            count = evaluation.enqueue_due_patients(session, as_of)
        return dataservice_pb2.EnqueueDuePatientsResponse(enqueued_count=count)

    def EnqueueAllPatients(self, request, context):
        with session_scope() as session:
            count = evaluation.enqueue_all_patients(session)
        return dataservice_pb2.EnqueueAllPatientsResponse(enqueued_count=count)


def _role_cache_key(role) -> str:
    return f"{role.role}:{','.join(sorted(role.allowed_task_types))}"


def _cached_page(cache_key: str, loader):
    """Worklist pages only (CLAUDE.md: patient detail is never cached). A
    cache hit skips `loader` entirely; a miss runs it and caches the plain
    dict result for `worklist_cache_ttl_seconds` under a key that already
    encodes the current `worklist:generation` counter, so `bump_generation`
    (called after every task write) retires every cached page at once
    without this function needing to know which pages a write could have
    affected."""
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached["items"], cached.get("next_cursor")
    items, next_cursor = loader()
    ttl = get_settings().worklist_cache_ttl_seconds
    cache_set_json(cache_key, {"items": items, "next_cursor": next_cursor}, ttl)
    return items, next_cursor


def _request_to_filter_dict(request) -> dict:
    """Best-effort dump of the scalar filter fields on a List* request, for
    the audit row. Never includes `role_filter`/`cursor` (not filters)."""
    out = {}
    for field in request.DESCRIPTOR.fields:
        if field.name in ("role_filter", "cursor"):
            continue
        if field.is_repeated:
            value = list(getattr(request, field.name))
            if value:
                out[field.name] = value
        elif request.HasField(field.name) if field.has_presence else getattr(request, field.name):
            out[field.name] = getattr(request, field.name)
    return out


def _need_result_from_proto(n) -> dict:
    # `next_check_candidate` is not read here: the engine already folds it
    # (and every `tier_recheck_at`) into the request's top-level
    # `next_eval_at`, which `SaveEvaluationResult` uses directly.
    return {
        "specialty": n.specialty,
        "cadence_days": n.cadence_days,
        "last_visit_date": date.fromisoformat(n.last_visit_date) if n.HasField("last_visit_date") else None,
        "due_date": date.fromisoformat(n.due_date) if n.HasField("due_date") else None,
        "has_upcoming": n.has_upcoming,
        "decision": n.decision,
    }


def _program_result_from_proto(p) -> dict:
    return {
        "program_id": p.program_id,
        "program_version": p.program_version,
        "eligible": p.eligible,
        "tier": p.tier if p.HasField("tier") else None,
        "needs": [_need_result_from_proto(n) for n in p.needs],
    }
