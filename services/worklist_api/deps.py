"""FastAPI dependencies: the role header ("auth") dependency and the gRPC
stub dependency.

No real auth in the MVP (see the plan's "Auth" decision) — `X-User-Role` and
`X-User-Id` are plain headers, read via an `APIKeyHeader` security scheme
each so Swagger's Authorize button can set them. `libs.common.roles` is the
single source of truth for role -> allowed task types; this module never
reimplements that mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from libs.common import errors, roles
from libs.common.grpc_client import data_service_stub
from libs.common.settings import get_settings

role_header_scheme = APIKeyHeader(
    name="X-User-Role",
    scheme_name="X-User-Role",
    auto_error=False,
    description="One of: scheduler, clinical, admin.",
)
user_header_scheme = APIKeyHeader(
    name="X-User-Id",
    scheme_name="X-User-Id",
    auto_error=False,
    description="Caller's user id (free text, no real auth in the MVP).",
)


@dataclass(frozen=True)
class Caller:
    role: str
    user_id: str
    allowed_task_types: tuple[str, ...]
    is_admin: bool


def get_caller(
    role: Annotated[str | None, Security(role_header_scheme)] = None,
    user_id: Annotated[str | None, Security(user_header_scheme)] = None,
) -> Caller:
    if not role or role not in roles.VALID_ROLES:
        # Assumption (see ASSUMPTIONS.md): missing/invalid X-User-Role is a
        # 422 validation error, not a 401 — reuses errors.ValidationError
        # rather than inventing a new AppError subclass.
        raise errors.ValidationError(
            f"Missing or invalid X-User-Role header; expected one of {roles.VALID_ROLES}"
        )
    return Caller(
        role=role,
        user_id=user_id or "",
        allowed_task_types=roles.allowed_task_types(role),
        is_admin=roles.is_admin(role),
    )


def require_admin(caller: Annotated[Caller, Depends(get_caller)]) -> Caller:
    if not caller.is_admin:
        # A flat 403: admin-only ops endpoints, not the task-visibility case
        # that specifically wants 404 to avoid leaking existence.
        raise errors.AppError(errors.FORBIDDEN, "Admin role required", 403)
    return caller


@lru_cache
def get_stub() -> Any:
    return data_service_stub(get_settings().data_service_target)


# Reusable dependency aliases so route handlers stay short — also the
# Annotated[...] form ruff/bugbear recognizes as exempt from B008
# ("function call in argument default"), unlike `x: T = Depends(...)`.
CallerDep = Annotated[Caller, Depends(get_caller)]
AdminDep = Annotated[Caller, Depends(require_admin)]
StubDep = Annotated[Any, Depends(get_stub)]
