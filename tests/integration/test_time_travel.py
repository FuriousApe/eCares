"""Time travel: flip `AS_OF_DATE` to 2026-05-08 on the live stack, re-run
evaluation for everyone, and compare the resulting `tasks` table against a
SEPARATE run of `tests/oracle.py` at that same date.

See `tests/ASSUMPTIONS.md` for exactly how `as_of_date_override` restarts
containers via a throwaway Compose override file and how it's restored
afterward -- this is the most operationally involved test in the suite.

**Ordering note.** Like `test_00_verification_numbers.py`, this compares a
live, mutable system against a stateless oracle snapshot; it assumes the
tasks table reflects nothing but "what the rules say for 2026-04-08" going
in (true right after `make seed`, and restored by every other file's own
teardown). For the cleanest signal, run it alone right after `make seed`.
"""

from __future__ import annotations

from datetime import date

import pytest

from libs.common.grpc_gen import dataservice_pb2 as pb
from tests.integration.support import as_of_date_override, run_oracle, wait_for_tasks_to_settle

NEW_AS_OF = date(2026, 5, 8)


def _paginate_tasks(client) -> list[dict]:
    items: list[dict] = []
    cursor = None
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = client.get("/tasks", params=params)
        resp.raise_for_status()
        body = resp.json()
        items.extend(body["items"])
        cursor = body.get("next_cursor")
        if not cursor:
            return items


@pytest.mark.slow
def test_moving_as_of_date_forward_matches_a_fresh_oracle_run(
    scheduler_client, clinical_client, grpc_stub, mysql_engine, api_base_url
):
    expected = run_oracle(NEW_AS_OF)

    with as_of_date_override(NEW_AS_OF, api_base_url):
        grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
        wait_for_tasks_to_settle(mysql_engine, timeout=180.0)

        scheduler_total = len(_paginate_tasks(scheduler_client))
        clinical_total = len(_paginate_tasks(clinical_client))

        assert scheduler_total == expected["tasks_scheduling"]
        assert clinical_total == expected["tasks_total"]

    # `as_of_date_override` already restored AS_OF_DATE=2026-04-08 and
    # restarted the affected containers on the way out; bring tasks back in
    # line with that date too, for whatever runs after this test.
    grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
    wait_for_tasks_to_settle(mysql_engine, timeout=180.0)
