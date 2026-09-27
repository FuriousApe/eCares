"""Error shapes shared between the Worklist API and the Data Service.

REST errors always look like `{code, message, request_id}` per the plan.
gRPC carries the same `code`/`message` via `grpc.StatusCode` + trailing
metadata so the API layer doesn't have to guess what went wrong.
"""

from __future__ import annotations

# Machine-readable codes used on both sides of the gRPC boundary.
NOT_FOUND = "not_found"
VERSION_CONFLICT = "version_conflict"
ILLEGAL_TRANSITION = "illegal_transition"
VALIDATION_ERROR = "validation_error"
FORBIDDEN = "forbidden"


class AppError(Exception):
    """Base for domain errors the Data Service raises and the API translates.

    `code` is one of the constants above; `http_status` is what the Worklist
    API should answer with (409 for a stale version, 422 for an illegal
    transition, 404 for a task the role may not see — never a 403 that would
    reveal a task exists but is hidden).
    """

    def __init__(self, code: str, message: str, http_status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(NOT_FOUND, message, 404)


class VersionConflictError(AppError):
    def __init__(self, message: str = "Version conflict"):
        super().__init__(VERSION_CONFLICT, message, 409)


class IllegalTransitionError(AppError):
    def __init__(self, message: str = "Illegal state transition"):
        super().__init__(ILLEGAL_TRANSITION, message, 422)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(VALIDATION_ERROR, message, 422)
