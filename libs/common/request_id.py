"""Request ID generation and propagation.

One id is created at the edge (HTTP middleware or a Kafka/timer trigger),
carried through the gRPC call in `RoleFilter`-adjacent metadata, and written
onto every audit row so a change can be traced back to what caused it.
"""

from __future__ import annotations

import contextvars
import uuid

_current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)

GRPC_METADATA_KEY = "x-request-id"


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(request_id: str) -> None:
    _current_request_id.set(request_id)


def get_request_id() -> str:
    rid = _current_request_id.get()
    if not rid:
        rid = new_request_id()
        _current_request_id.set(rid)
    return rid
