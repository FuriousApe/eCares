"""Worklist API — FastAPI app exposing the Care Gap Engine's REST surface
over the Data Service's gRPC contract. Swagger docs come for free from
FastAPI/Pydantic v2 at `/docs`.

Runs via `uvicorn` when `ROLE=worklist-api` (see `run.py` at the repo root).
See `services/worklist_api/ASSUMPTIONS.md` for the gRPC-error -> HTTP-status
mapping and the `/admin/*` wiring decisions.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from libs.common import errors
from libs.common.logging import configure_logging
from libs.common.request_id import get_request_id, new_request_id, set_request_id
from libs.common.settings import get_settings
from services.worklist_api.routers import admin, health, meta, patients, programs, tasks

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Care Gap Engine — Worklist API",
        description="Role-scoped worklist REST API over the Data Service gRPC contract.",
        version="0.1.0",
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or new_request_id()
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(errors.AppError)
    async def app_error_handler(request: Request, exc: errors.AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "request_id": get_request_id()},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error in worklist_api")
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": get_request_id(),
            },
        )

    for router in (health, meta, patients, tasks, programs, admin):
        app.include_router(router.router)

    # The dashboard (services/ui) is served from :3000 and calls this API cross-origin.
    # Added last so it wraps everything, including error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    configure_logging("worklist-api")
    uvicorn.run(app, host="0.0.0.0", port=get_settings().http_port)


if __name__ == "__main__":
    main()
