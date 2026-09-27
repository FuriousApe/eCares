"""Idempotency: evaluate everyone twice in a row and assert the second run
changes nothing in `tasks` (the plan's Verification section; CLAUDE.md #7's
idempotency-key mechanism is what should make this true).

`EnqueueAllPatients` only enqueues every patient onto Kafka's `patient.changed`
topic -- the actual evaluation happens asynchronously in the engine consumer,
so "the run finished" is never a single RPC response. It is polled for: the
`tasks` table's (row count, MAX(updated_at)) fingerprint settling for a few
consecutive checks (`support.wait_for_tasks_to_settle`), never a fixed sleep.
"""

from __future__ import annotations

from libs.common.grpc_gen import dataservice_pb2 as pb
from tests.integration.support import snapshot_tasks, wait_for_tasks_to_settle


def _enqueue_all_and_settle(grpc_stub, mysql_engine) -> None:
    grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
    wait_for_tasks_to_settle(mysql_engine)


def test_second_full_evaluation_run_changes_nothing(grpc_stub, mysql_engine):
    # Settle any state left by earlier test files before taking the "before"
    # snapshot, so only this test's own two runs are the source of change
    # being measured.
    _enqueue_all_and_settle(grpc_stub, mysql_engine)
    before = snapshot_tasks(mysql_engine)

    _enqueue_all_and_settle(grpc_stub, mysql_engine)
    after = snapshot_tasks(mysql_engine)

    assert after == before, (
        f"Re-running evaluation for everyone changed the tasks table "
        f"(before had {len(before)} rows, after had {len(after)})."
    )
