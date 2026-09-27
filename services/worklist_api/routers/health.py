"""GET /health — liveness only. No role required, no Data Service call."""

from __future__ import annotations

from fastapi import APIRouter

from services.worklist_api.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut()
