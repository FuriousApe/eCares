"""Redis access: the worklist generation counter and the two caches the plan
names — `worklist:{generation}:{hash}` pages and `programs:active`.

Caching is best-effort: if Redis is unreachable, reads still work (they just
skip the cache), because correctness of a worklist page never depends on
Redis, only its latency does. Every call is wrapped so a Redis outage can't
turn into a 500 for a read RPC.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis

from libs.common.settings import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None

GENERATION_KEY = "worklist:generation"
PROGRAMS_ACTIVE_KEY = "programs:active"


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        s = get_settings()
        # Short timeouts so an unreachable Redis fails fast into `_safe`'s
        # `except redis.RedisError` below instead of hanging the calling RPC
        # on a TCP connect (redis-py sets none by default).
        _client = redis.Redis(
            host=s.redis_host,
            port=s.redis_port,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def _safe(fn, default=None):  # noqa: ANN001 - tiny local helper, not public API
    try:
        return fn()
    except redis.RedisError as exc:
        logger.warning("redis unavailable: %s", exc)
        return default


def get_generation() -> int:
    value = _safe(lambda: get_client().get(GENERATION_KEY))
    return int(value) if value else 0


def bump_generation() -> None:
    """Called at the end of every state-changing RPC. One counter bump
    retires every cached worklist page at once — cheaper and simpler than
    tracking which pages a given write could have affected."""
    _safe(lambda: get_client().incr(GENERATION_KEY))


def worklist_cache_key(role_filter_key: str, filters: dict[str, Any], cursor: str | None) -> str:
    generation = get_generation()
    payload = json.dumps(
        {"role": role_filter_key, "filters": filters, "cursor": cursor},
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:24]
    return f"worklist:{generation}:{digest}"


def cache_get_json(key: str) -> Any | None:
    raw = _safe(lambda: get_client().get(key))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    _safe(lambda: get_client().set(key, json.dumps(value, default=str), ex=ttl_seconds))


def set_active_programs(programs_json: list[dict[str, Any]]) -> None:
    _safe(lambda: get_client().set(PROGRAMS_ACTIVE_KEY, json.dumps(programs_json)))


def get_active_programs() -> list[dict[str, Any]] | None:
    return cache_get_json(PROGRAMS_ACTIVE_KEY)
