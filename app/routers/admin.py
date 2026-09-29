from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.engine.recompute import DEFAULT_AS_OF_DATE, recompute_all

router = APIRouter(tags=["admin"])

PROGRAMS_DIR = str(Path(__file__).resolve().parent.parent.parent / "programs")


@router.post("/admin/recompute")
def admin_recompute(db: Session = Depends(get_session)):
    return recompute_all(db, PROGRAMS_DIR, DEFAULT_AS_OF_DATE)
