from __future__ import annotations

from libs.common.request_id import GRPC_METADATA_KEY


def test_generated_request_id_on_success(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    rid = resp.headers["x-request-id"]
    assert rid  # generated, non-empty


def test_generated_request_id_on_error(client):
    resp = client.get("/tasks")  # missing role header -> 422
    assert resp.status_code == 422
    assert resp.headers["x-request-id"]
    assert resp.json()["request_id"] == resp.headers["x-request-id"]


def test_supplied_request_id_is_echoed_and_forwarded_to_grpc(client, fake_stub):
    resp = client.get(
        "/meta",
        headers={"X-User-Role": "admin", "X-Request-Id": "my-fixed-request-id"},
    )
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "my-fixed-request-id"

    _, _, metadata = fake_stub.calls[-1]
    assert dict(metadata)[GRPC_METADATA_KEY] == "my-fixed-request-id"
