from __future__ import annotations

import pytest


def test_missing_role_header_rejected(client):
    resp = client.get("/tasks")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert "request_id" in body


def test_invalid_role_header_rejected(client):
    resp = client.get("/tasks", headers={"X-User-Role": "superuser"})
    assert resp.status_code == 422


@pytest.mark.parametrize("role", ["scheduler", "clinical", "admin"])
def test_valid_roles_accepted(client, role):
    resp = client.get("/tasks", headers={"X-User-Role": role})
    assert resp.status_code == 200
