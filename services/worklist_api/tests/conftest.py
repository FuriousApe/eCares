"""Test fixtures: a FastAPI TestClient wired to a fake, in-process
DataServiceStub (no live Data Service / gRPC network calls in these tests).
"""

from __future__ import annotations

import os

import grpc
import pytest
from fastapi.testclient import TestClient

from libs.common.grpc_gen import dataservice_pb2 as pb
from services.worklist_api.deps import get_stub
from services.worklist_api.main import app

# Match the deployed default (docker-compose.yml) so AS_OF_DATE-dependent
# behavior (days_overdue) is deterministic in tests, not tied to wall-clock
# "today". Settings are read lazily (get_settings() is only called inside
# request handlers), so this just needs to run before any test executes.
os.environ.setdefault("AS_OF_DATE", "2026-04-08")

# Sentinel task ids the fake stub uses to simulate specific Data Service
# error signals, per services/worklist_api/ASSUMPTIONS.md's gRPC mapping.
STALE_VERSION_TASK_ID = 999
ALREADY_COMPLETED_TASK_ID = 998
HIDDEN_TASK_ID = 777


class FakeRpcError(grpc.RpcError):
    """A minimal stand-in for a real grpc.RpcError, carrying just what
    `grpc_calls.call` inspects: `.code()`, `.details()`, `.trailing_metadata()`.
    """

    def __init__(self, code: grpc.StatusCode, details: str, app_code: str | None = None):
        super().__init__(details)
        self._code = code
        self._details = details
        self._trailing = (("code", app_code),) if app_code else ()

    def code(self):
        return self._code

    def details(self):
        return self._details

    def trailing_metadata(self):
        return self._trailing


def _task(task_id: int = 1, **overrides) -> pb.Task:
    fields = dict(
        task_id=task_id,
        patient_id="P0001",
        program_id="diabetes_management",
        tier="high_risk",
        specialty="Endocrinology",
        task_type="referral",
        status="open",
        due_date="2026-01-01",
        program_version=1,
        version=1,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    fields.update(overrides)
    return pb.Task(**fields)


class FakeStub:
    """Fake DataServiceStub. Records every call as (method_name, request,
    metadata) in `self.calls`, so tests can assert what was forwarded (e.g.
    the request id metadata, or the role filter)."""

    def __init__(self):
        self.calls: list[tuple[str, object, object]] = []
        self._sync_runs: list[pb.SyncRun] = []

    def _record(self, name, request, metadata):
        self.calls.append((name, request, metadata))

    # --- interactive read ---

    def GetMeta(self, request, metadata=None):
        self._record("GetMeta", request, metadata)
        resp = pb.GetMetaResponse(as_of_date="2026-04-08")
        resp.task_counts_by_status["open"] = 5
        resp.task_counts_by_status["completed"] = 2
        return resp

    def ListPatients(self, request, metadata=None):
        self._record("ListPatients", request, metadata)
        return pb.ListPatientsResponse(items=[])

    def GetPatient(self, request, metadata=None):
        self._record("GetPatient", request, metadata)
        if request.patient_id == "P9999":
            raise FakeRpcError(grpc.StatusCode.NOT_FOUND, "no such patient", "not_found")
        patient = pb.Patient(
            patient_id=request.patient_id,
            first_name="Jane",
            last_name="Doe",
            date_of_birth="1970-01-01",
            gender="F",
            phone="555-0100",
            language="en",
            age=56,
        )
        return pb.GetPatientResponse(patient=patient, enrollments=[], needs=[], visible_tasks=[])

    def ListTasks(self, request, metadata=None):
        self._record("ListTasks", request, metadata)
        # Mirrors the Data Service's real behavior: a filter for a task_type
        # outside the caller's role_filter.allowed_task_types yields an
        # empty page, never an error.
        if request.task_type and request.task_type not in request.role_filter.allowed_task_types:
            return pb.ListTasksResponse(items=[])
        return pb.ListTasksResponse(items=[_task()], next_cursor=None)

    def GetTask(self, request, metadata=None):
        self._record("GetTask", request, metadata)
        if request.task_id == HIDDEN_TASK_ID:
            raise FakeRpcError(grpc.StatusCode.NOT_FOUND, "not visible to this role", "not_found")
        return pb.GetTaskResponse(task=_task(task_id=request.task_id), history=[])

    def ListPrograms(self, request, metadata=None):
        self._record("ListPrograms", request, metadata)
        return pb.ListProgramsResponse(items=[])

    # --- interactive write ---

    def ClaimTask(self, request, metadata=None):
        self._record("ClaimTask", request, metadata)
        return pb.TaskResponse(
            task=_task(task_id=request.task_id, status="in_progress", version=request.version + 1)
        )

    def CompleteTask(self, request, metadata=None):
        self._record("CompleteTask", request, metadata)
        if request.task_id == STALE_VERSION_TASK_ID:
            raise FakeRpcError(grpc.StatusCode.ABORTED, "stale version", "version_conflict")
        if request.task_id == ALREADY_COMPLETED_TASK_ID:
            raise FakeRpcError(
                grpc.StatusCode.FAILED_PRECONDITION,
                "task is already completed",
                "illegal_transition",
            )
        return pb.TaskResponse(
            task=_task(
                task_id=request.task_id,
                status="completed",
                resolution=request.resolution,
                version=request.version + 1,
            )
        )

    def DeclineTask(self, request, metadata=None):
        self._record("DeclineTask", request, metadata)
        return pb.TaskResponse(
            task=_task(task_id=request.task_id, status="declined", version=request.version + 1)
        )

    def SnoozeTask(self, request, metadata=None):
        self._record("SnoozeTask", request, metadata)
        return pb.TaskResponse(
            task=_task(
                task_id=request.task_id,
                status="open",
                snooze_until=request.until,
                version=request.version + 1,
            )
        )

    # --- bulk / admin ---

    def StartSyncRun(self, request, metadata=None):
        self._record("StartSyncRun", request, metadata)
        return pb.StartSyncRunResponse(run_id="run-1")

    def UpsertFacts(self, request, metadata=None):
        # /admin/sync now drives services.sync.main.run_sync() for real
        # (CLAUDE.md decision #15), which sends every row from the real
        # ecares/data/*.csv files through here in chunks — this fake just
        # accepts everything, mirroring a Data Service with no rejections.
        self._record("UpsertFacts", request, metadata)
        return pb.UpsertFactsResponse(accepted_count=len(request.rows), rejected=[])

    def CompleteSyncRun(self, request, metadata=None):
        self._record("CompleteSyncRun", request, metadata)
        run = pb.SyncRun(
            run_id=request.run_id,
            status=request.status,
            started_at="2026-04-08T00:00:00",
            counts_json="{}",
            watermarks_json="{}",
        )
        self._sync_runs.insert(0, run)  # most recent first, like a real ledger
        return pb.CompleteSyncRunResponse(run=run, changed_patient_ids=[])

    def ListSyncRuns(self, request, metadata=None):
        self._record("ListSyncRuns", request, metadata)
        limit = request.limit or len(self._sync_runs)
        return pb.ListSyncRunsResponse(items=self._sync_runs[:limit])

    def EnqueueDuePatients(self, request, metadata=None):
        self._record("EnqueueDuePatients", request, metadata)
        return pb.EnqueueDuePatientsResponse(enqueued_count=3)

    def EnqueueAllPatients(self, request, metadata=None):
        self._record("EnqueueAllPatients", request, metadata)
        return pb.EnqueueAllPatientsResponse(enqueued_count=300)


@pytest.fixture
def fake_stub() -> FakeStub:
    return FakeStub()


@pytest.fixture
def client(fake_stub: FakeStub):
    app.dependency_overrides[get_stub] = lambda: fake_stub
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
