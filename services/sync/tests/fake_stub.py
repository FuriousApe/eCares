"""A fake Data Service stub for sync tests -- no live gRPC server needed.

Records every call it receives and lets a test script transient failures
for `UpsertFacts` (to exercise the retry path) and canned rejected rows (to
exercise the "Data Service rejected some rows" logging path).
"""

from __future__ import annotations

import grpc

from libs.common.grpc_gen import dataservice_pb2 as pb


class FakeRpcError(grpc.RpcError):
    """Minimal stand-in for grpcio's real `_InactiveRpcError`: just `.code()`."""

    def __init__(self, code: grpc.StatusCode):
        super().__init__(str(code))
        self._code = code

    def code(self) -> grpc.StatusCode:
        return self._code


class FakeDataServiceStub:
    def __init__(
        self,
        fail_upsert_times: int = 0,
        fail_code: grpc.StatusCode = grpc.StatusCode.UNAVAILABLE,
        rejects_first_chunk: dict[str, list[tuple[dict[str, str], str]]] | None = None,
        run_id: str = "run-123",
    ):
        self.calls: list[tuple[str, object]] = []
        self.fail_upsert_times = fail_upsert_times
        self.fail_code = fail_code
        self.rejects_first_chunk = rejects_first_chunk or {}
        self.run_id = run_id
        self._upsert_attempts: dict[tuple[str, int], int] = {}

    def StartSyncRun(self, request, metadata=None):
        self.calls.append(("StartSyncRun", request))
        return pb.StartSyncRunResponse(run_id=self.run_id)

    def UpsertFacts(self, request, metadata=None):
        self.calls.append(("UpsertFacts", request))
        key = (request.resource_type, request.chunk_number)
        attempts = self._upsert_attempts.get(key, 0) + 1
        self._upsert_attempts[key] = attempts
        if attempts <= self.fail_upsert_times:
            raise FakeRpcError(self.fail_code)

        rejected = []
        if request.chunk_number == 0:
            for raw, reason in self.rejects_first_chunk.get(request.resource_type, []):
                rejected.append(pb.RejectedRow(raw=raw, reason=reason))
        accepted = len(request.rows) - len(rejected)
        return pb.UpsertFactsResponse(accepted_count=accepted, rejected=rejected)

    def CompleteSyncRun(self, request, metadata=None):
        self.calls.append(("CompleteSyncRun", request))
        run = pb.SyncRun(
            run_id=request.run_id,
            status=request.status,
            started_at="2026-04-08T00:00:00",
            counts_json="{}",
        )
        return pb.CompleteSyncRunResponse(run=run, changed_patient_ids=["P0001", "P0002"])
