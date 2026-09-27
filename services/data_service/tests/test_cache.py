"""Redis helper behavior — no real Redis: `get_client`/`get_generation` are
monkeypatched so these stay fast, deterministic unit tests. Covers the two
things the plan actually depends on: a broken Redis degrades to a default
instead of raising, and the generation counter is what makes
`worklist_cache_key` change on a bump (the invalidation scheme).
"""

from __future__ import annotations

import redis

from services.data_service import cache


class _BrokenClient:
    def get(self, key):
        raise redis.RedisError("down")

    def incr(self, key):
        raise redis.RedisError("down")

    def set(self, *args, **kwargs):
        raise redis.RedisError("down")


def test_safe_helpers_degrade_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "get_client", lambda: _BrokenClient())
    assert cache.get_generation() == 0
    cache.bump_generation()  # must not raise
    assert cache.cache_get_json("k") is None
    cache.cache_set_json("k", {"a": 1}, 30)  # must not raise


def test_worklist_cache_key_changes_when_generation_bumps(monkeypatch):
    gens = iter([0, 1])
    monkeypatch.setattr(cache, "get_generation", lambda: next(gens))
    key1 = cache.worklist_cache_key("role", {"a": 1}, None)
    key2 = cache.worklist_cache_key("role", {"a": 1}, None)
    assert key1 != key2
    assert key1.startswith("worklist:0:")
    assert key2.startswith("worklist:1:")


def test_worklist_cache_key_stable_regardless_of_filter_key_order(monkeypatch):
    monkeypatch.setattr(cache, "get_generation", lambda: 3)
    key_a = cache.worklist_cache_key("role", {"a": 1, "b": 2}, "cur")
    key_b = cache.worklist_cache_key("role", {"b": 2, "a": 1}, "cur")
    assert key_a == key_b


def test_worklist_cache_key_differs_by_role_or_cursor(monkeypatch):
    monkeypatch.setattr(cache, "get_generation", lambda: 0)
    base = cache.worklist_cache_key("scheduler", {}, None)
    assert base != cache.worklist_cache_key("clinical", {}, None)
    assert base != cache.worklist_cache_key("scheduler", {}, "c1")
