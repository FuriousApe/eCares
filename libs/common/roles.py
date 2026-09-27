"""Role → visibility mapping, shared so the Worklist API and any test code
agree on exactly what each `X-User-Role` may see.

The Data Service never hard-codes this: it only ever receives the resolved
`allowed_task_types` list inside `RoleFilter` and applies it in the SQL
`WHERE`. This module is the one place the role→task_type mapping lives.
"""

from __future__ import annotations

VALID_ROLES = ("scheduler", "clinical", "admin")

_ALLOWED_TASK_TYPES: dict[str, tuple[str, ...]] = {
    "scheduler": ("scheduling",),
    "clinical": ("scheduling", "referral"),
    "admin": ("scheduling", "referral"),
}


def allowed_task_types(role: str) -> tuple[str, ...]:
    return _ALLOWED_TASK_TYPES.get(role, ())


def is_admin(role: str) -> bool:
    return role == "admin"
