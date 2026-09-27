"""`servicer._cached_page`, the ListPatients/ListTasks caching wrapper — no
real Redis or gRPC server: `cache_get_json`/`cache_set_json` are monkeypatched
directly on the `servicer` module (that's where the `from ... import` bound
them). Covers a cache hit skipping the loader entirely and a miss caching
what the loader returned, which is the whole generation-counter invalidation
scheme's payoff (see `test_cache.py` for the key itself changing on a bump).
"""

from __future__ import annotations

from services.data_service import servicer


def test_cache_hit_skips_the_loader(monkeypatch):
    cached_page = {"items": ["cached"], "next_cursor": None}
    monkeypatch.setattr(servicer, "cache_get_json", lambda key: cached_page)
    calls = []

    def loader():
        calls.append(1)
        return ["fresh"], "should-not-be-used"

    items, next_cursor = servicer._cached_page("k", loader)
    assert items == ["cached"]
    assert next_cursor is None
    assert calls == []  # loader (the DB query) never ran


def test_cache_miss_runs_the_loader_and_stores_the_result(monkeypatch):
    monkeypatch.setattr(servicer, "cache_get_json", lambda key: None)
    stored = {}
    monkeypatch.setattr(
        servicer, "cache_set_json", lambda key, value, ttl: stored.__setitem__(key, value)
    )
    items, next_cursor = servicer._cached_page("k", lambda: (["fresh"], "c2"))
    assert items == ["fresh"]
    assert next_cursor == "c2"
    assert stored["k"] == {"items": ["fresh"], "next_cursor": "c2"}


def test_role_cache_key_is_stable_regardless_of_allowed_task_type_order():
    from types import SimpleNamespace

    role_a = SimpleNamespace(role="clinical", allowed_task_types=["referral", "scheduling"])
    role_b = SimpleNamespace(role="clinical", allowed_task_types=["scheduling", "referral"])
    assert servicer._role_cache_key(role_a) == servicer._role_cache_key(role_b)
