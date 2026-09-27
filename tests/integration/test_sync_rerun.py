"""Sync rerun: `POST /admin/sync` twice in a row against unchanged CSVs must
report an empty `changed_patient_ids` on the second call and write zero new
`outbox` rows.

Calls it twice itself (rather than assuming `make seed` already ran once)
so this test is self-contained regardless of what already happened to the
stack: the first call here is whatever "first or Nth" sync it happens to be,
and only the *second* call's behavior is asserted on.
"""

from __future__ import annotations

from tests.integration.support import count_outbox_rows


def test_second_sync_run_changes_nothing(admin_client, mysql_engine):
    first = admin_client.post("/admin/sync")
    first.raise_for_status()

    before_outbox = count_outbox_rows(mysql_engine)

    second = admin_client.post("/admin/sync")
    second.raise_for_status()
    body = second.json()

    assert body["changed_patient_ids"] == []

    after_outbox = count_outbox_rows(mysql_engine)
    assert after_outbox == before_outbox
