"""Decline: claim + decline a real open scheduling task with a short
snooze, re-evaluate and confirm no task reappears while snoozed, then jump
`AS_OF_DATE` past the snooze and confirm the task DOES reappear.

The second half reuses the same `as_of_date_override` mechanism
`test_time_travel.py` uses (see `tests/ASSUMPTIONS.md` for exactly what that
does and its known limits). The jump here is tiny and deliberately
independent of any specific patient's cadence math: whatever task gets
picked, if its underlying need was unmet before the decline, it is still
unmet two days later -- the ONLY thing gating task recreation across that gap
is the snooze itself, which is exactly the mechanic being proven.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from libs.common.grpc_gen import dataservice_pb2 as pb
from tests.integration.support import (
    as_of_date_override,
    count_open_tasks_for_key,
    wait_for_tasks_to_settle,
)

SNOOZE_DAYS = 1


def _pick_open_scheduling_task(clinical_client) -> dict:
    resp = clinical_client.get(
        "/tasks", params={"task_type": "scheduling", "status": "open", "limit": 1}
    )
    resp.raise_for_status()
    items = resp.json()["items"]
    assert items, "Expected at least one open scheduling task to decline (fresh seed has 154)."
    return items[0]


@pytest.mark.slow
def test_decline_then_snooze_then_time_travel_recreates_task(
    clinical_client, grpc_stub, mysql_engine, api_base_url
):
    task = _pick_open_scheduling_task(clinical_client)
    task_id = task["task_id"]
    patient_id, program_id, specialty = task["patient_id"], task["program_id"], task["specialty"]

    claim = clinical_client.post(f"/tasks/{task_id}/claim", json={"version": task["version"]})
    claim.raise_for_status()
    claimed_version = claim.json()["version"]

    decline = clinical_client.post(
        f"/tasks/{task_id}/decline",
        json={
            "version": claimed_version,
            "reason": "patient asked to be called back later",
            "snooze_days": SNOOZE_DAYS,
        },
    )
    decline.raise_for_status()
    declined = decline.json()
    assert declined["status"] == "declined"
    assert declined["snooze_until"] is not None

    # Re-run evaluation for everyone; the still-snoozed key must get no new
    # open task.
    grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
    wait_for_tasks_to_settle(mysql_engine)
    assert count_open_tasks_for_key(mysql_engine, patient_id, program_id, specialty) == 0

    with mysql_engine.connect() as conn:
        snooze_until = conn.execute(
            sa.text("SELECT snooze_until FROM tasks WHERE task_id=:t"), {"t": task_id}
        ).scalar_one()
    new_as_of = snooze_until + timedelta(days=1)  # one day past the snooze -> unblocked

    with as_of_date_override(new_as_of, api_base_url):
        grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
        wait_for_tasks_to_settle(mysql_engine)
        assert count_open_tasks_for_key(mysql_engine, patient_id, program_id, specialty) == 1

    # `as_of_date_override`'s own teardown already restored AS_OF_DATE and
    # restarted the affected containers; re-settle tasks here so the table
    # reflects that restored date again for whatever test runs next.
    grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
    wait_for_tasks_to_settle(mysql_engine)
