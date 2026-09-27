from __future__ import annotations

import pytest


@pytest.mark.parametrize("role", ["scheduler", "clinical"])
@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("post", "/admin/sync", {}),
        ("post", "/admin/evaluate", {"params": {"all": "true"}}),
        ("get", "/admin/sync-runs", {}),
    ],
)
def test_non_admin_rejected(client, role, method, path, kwargs):
    resp = getattr(client, method)(path, headers={"X-User-Role": role}, **kwargs)
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_admin_sync_triggers_a_run(client):
    resp = client.post("/admin/sync", headers={"X-User-Role": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["run_id"] == "run-1"
    assert body["run"]["status"] == "completed"


def test_admin_evaluate_all(client):
    resp = client.post(
        "/admin/evaluate", params={"all": "true"}, headers={"X-User-Role": "admin"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"enqueued_count": 300, "scope": "all", "note": None}


def test_admin_evaluate_single_patient(client):
    resp = client.post(
        "/admin/evaluate",
        params={"patient_id": "P0001"},
        headers={"X-User-Role": "admin"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "patient"
    assert body["note"] is not None


def test_admin_evaluate_requires_exactly_one_of_patient_id_or_all(client):
    resp = client.post("/admin/evaluate", headers={"X-User-Role": "admin"})
    assert resp.status_code == 422

    resp = client.post(
        "/admin/evaluate",
        params={"patient_id": "P0001", "all": "true"},
        headers={"X-User-Role": "admin"},
    )
    assert resp.status_code == 422


def test_admin_sync_runs_list(client):
    resp = client.get("/admin/sync-runs", headers={"X-User-Role": "admin"})
    assert resp.status_code == 200
    assert resp.json() == {"items": []}
