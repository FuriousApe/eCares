"""Roles: a scheduler asking for referral tasks gets an empty page (200, not
an error that would leak that referral tasks exist -- CLAUDE.md #6); a
clinical user asking the same question gets real rows.
"""

from __future__ import annotations


def test_scheduler_cannot_see_referral_tasks(scheduler_client):
    resp = scheduler_client.get("/tasks", params={"task_type": "referral"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_clinical_can_see_referral_tasks(clinical_client):
    resp = clinical_client.get("/tasks", params={"task_type": "referral"})
    assert resp.status_code == 200
    # The oracle puts 119 referral tasks in a fresh seed; not asserting the
    # exact count here (that's test_00_verification_numbers.py's job, and
    # this file doesn't want to depend on running before/after the tests
    # that mutate task state) -- just that clinical genuinely sees some.
    assert len(resp.json()["items"]) > 0
