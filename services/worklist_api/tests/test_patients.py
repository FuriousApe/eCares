from __future__ import annotations


def test_list_patients_requires_role(client):
    resp = client.get("/patients")
    assert resp.status_code == 422


def test_list_patients_ok(client):
    resp = client.get("/patients", headers={"X-User-Role": "clinical"})
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


def test_get_patient_not_found(client):
    resp = client.get("/patients/P9999", headers={"X-User-Role": "clinical"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_get_patient_found(client):
    resp = client.get("/patients/P0001", headers={"X-User-Role": "scheduler"})
    assert resp.status_code == 200
    assert resp.json()["patient"]["patient_id"] == "P0001"
