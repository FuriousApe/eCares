"""Call the Data Service and translate a gRPC failure into the matching
`AppError` subclass. See ASSUMPTIONS.md for the full gRPC-code -> HTTP-status
mapping this implements.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import grpc

from libs.common import errors
from libs.common.grpc_client import call_metadata

# Plain TypeVar, not PEP 695 `def call[T]`, so this still runs on the host's
# Python 3.10 (pure-logic tests are run there per ASSUMPTIONS.md #4) even
# though the Docker image targets 3.12.
T = TypeVar("T")

# Preferred: the Data Service's trailing metadata carries the same `code`
# constant the REST layer already uses (see libs/common/errors.py).
_CODE_TO_ERROR: dict[str, type[errors.AppError]] = {
    errors.NOT_FOUND: errors.NotFoundError,
    errors.VERSION_CONFLICT: errors.VersionConflictError,
    errors.ILLEGAL_TRANSITION: errors.IllegalTransitionError,
    errors.VALIDATION_ERROR: errors.ValidationError,
}

# Fallback: a 1:1 mapping from the gRPC status code, in case the Data
# Service only sets the status and not the trailing-metadata `code`.
_STATUS_TO_ERROR: dict[grpc.StatusCode, type[errors.AppError]] = {
    grpc.StatusCode.NOT_FOUND: errors.NotFoundError,
    grpc.StatusCode.ABORTED: errors.VersionConflictError,
    grpc.StatusCode.FAILED_PRECONDITION: errors.IllegalTransitionError,
    grpc.StatusCode.INVALID_ARGUMENT: errors.ValidationError,
}


def call(rpc: Callable[..., T], request: Any) -> T:
    """Call `rpc(request)`, forwarding the current request id as gRPC
    metadata and re-raising a failure as an `AppError` the app's exception
    handler already knows how to render."""
    try:
        return rpc(request, metadata=call_metadata())
    except grpc.RpcError as exc:
        app_code = None
        for key, value in exc.trailing_metadata() or ():
            if key == "code":
                app_code = value
                break
        error_cls = _CODE_TO_ERROR.get(app_code) or _STATUS_TO_ERROR.get(exc.code())
        if error_cls is None:
            raise
        details = exc.details()
        err = error_cls(details) if details else error_cls()
        raise err from exc
