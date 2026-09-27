from services.data_service.hashing import idempotency_key, row_hash, snapshot_hash


def test_row_hash_stable_regardless_of_key_order():
    assert row_hash({"a": "1", "b": "2"}) == row_hash({"b": "2", "a": "1"})


def test_row_hash_changes_when_a_value_changes():
    assert row_hash({"a": "1"}) != row_hash({"a": "2"})


def test_snapshot_hash_stable_regardless_of_key_order():
    assert snapshot_hash({"x": 1, "y": 2}) == snapshot_hash({"y": 2, "x": 1})


def test_idempotency_key_is_deterministic_per_patient_and_snapshot():
    sh = snapshot_hash({"x": 1})
    assert idempotency_key("P1", sh) == idempotency_key("P1", sh)


def test_idempotency_key_differs_per_patient():
    sh = snapshot_hash({"x": 1})
    assert idempotency_key("P1", sh) != idempotency_key("P2", sh)


def test_idempotency_key_differs_when_snapshot_changes():
    key_a = idempotency_key("P1", snapshot_hash({"x": 1}))
    key_b = idempotency_key("P1", snapshot_hash({"x": 2}))
    assert key_a != key_b
