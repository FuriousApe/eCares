from __future__ import annotations


def test_health_needs_no_role_header(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["x-request-id"]


def test_meta_requires_role_header(client):
    resp = client.get("/meta")
    assert resp.status_code == 422
    body = resp.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "validation_error"


def test_meta_ok_with_role(client):
    resp = client.get("/meta", headers={"X-User-Role": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of_date"] == "2026-04-08"
    assert body["task_counts_by_status"] == {"open": 5, "completed": 2}
