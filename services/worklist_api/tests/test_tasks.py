from __future__ import annotations

from services.worklist_api.tests.conftest import (
    ALREADY_COMPLETED_TASK_ID,
    HIDDEN_TASK_ID,
    STALE_VERSION_TASK_ID,
)


def test_scheduler_asking_for_referral_gets_empty_list_not_an_error(client):
    resp = client.get(
        "/tasks", params={"task_type": "referral"}, headers={"X-User-Role": "scheduler"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_clinical_asking_for_referral_gets_results(client):
    resp = client.get(
        "/tasks", params={"task_type": "referral"}, headers={"X-User-Role": "clinical"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_scheduler_role_filter_sent_to_data_service(client, fake_stub):
    client.get("/tasks", headers={"X-User-Role": "scheduler"})
    _, request, _ = fake_stub.calls[-1]
    assert list(request.role_filter.allowed_task_types) == ["scheduling"]
    assert request.role_filter.role == "scheduler"


def test_complete_with_stale_version_is_409(client):
    resp = client.post(
        f"/tasks/{STALE_VERSION_TASK_ID}/complete",
        json={"version": 1, "resolution": "booked"},
        headers={"X-User-Role": "clinical"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "version_conflict"


def test_complete_illegal_transition_is_422(client):
    resp = client.post(
        f"/tasks/{ALREADY_COMPLETED_TASK_ID}/complete",
        json={"version": 1, "resolution": "booked"},
        headers={"X-User-Role": "clinical"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "illegal_transition"


def test_complete_rejects_bad_resolution_before_calling_data_service(client, fake_stub):
    resp = client.post(
        "/tasks/1/complete",
        json={"version": 1, "resolution": "not_a_real_resolution"},
        headers={"X-User-Role": "clinical"},
    )
    assert resp.status_code == 422
    assert fake_stub.calls == []  # never reached the gRPC layer


def test_hidden_task_is_404_not_403_or_empty_200(client):
    resp = client.get(f"/tasks/{HIDDEN_TASK_ID}", headers={"X-User-Role": "scheduler"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "not_found"


def test_limit_above_200_is_rejected(client):
    resp = client.get("/tasks", params={"limit": 500}, headers={"X-User-Role": "clinical"})
    assert resp.status_code == 422


def test_limit_at_200_is_accepted(client):
    resp = client.get("/tasks", params={"limit": 200}, headers={"X-User-Role": "clinical"})
    assert resp.status_code == 200


def test_claim_task(client):
    resp = client.post(
        "/tasks/1/claim", json={"version": 1}, headers={"X-User-Role": "clinical"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


def test_decline_task_default_snooze_days(client, fake_stub):
    resp = client.post(
        "/tasks/1/decline",
        json={"version": 1, "reason": "patient declined"},
        headers={"X-User-Role": "clinical"},
    )
    assert resp.status_code == 200
    _, request, _ = fake_stub.calls[-1]
    assert request.snooze_days == 90


def test_snooze_task(client):
    resp = client.post(
        "/tasks/1/snooze",
        json={"version": 1, "until": "2026-06-01", "reason": "call back later"},
        headers={"X-User-Role": "clinical"},
    )
    assert resp.status_code == 200
    assert resp.json()["snooze_until"] == "2026-06-01"


def test_days_overdue_computed_when_data_service_omits_it(client):
    # The fake stub's default task has due_date 2026-01-01 and no
    # days_overdue set on the wire; conftest pins AS_OF_DATE=2026-04-08, so
    # the API layer must compute it itself from due_date.
    resp = client.get("/tasks/1", headers={"X-User-Role": "clinical"})
    assert resp.status_code == 200
    assert resp.json()["task"]["days_overdue"] == 97
