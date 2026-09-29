from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import SEED_USERS
from app.db import DB_PATH, SessionLocal, engine
from app.engine.recompute import DEFAULT_AS_OF_DATE, recompute_all
from app.ingest import ingest_all
from app.models import Base, Patient, User
from app.routers import admin, auth, patients, tasks

PROGRAMS_DIR = str(Path(__file__).resolve().parent.parent / "programs")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        if session.query(Patient).first() is None:
            ingest_all(session)
            for u in SEED_USERS:
                if session.get(User, u["id"]) is None:
                    session.add(User(id=u["id"], name=u["name"], role=u["role"]))
            session.commit()
            recompute_all(session, PROGRAMS_DIR, DEFAULT_AS_OF_DATE)
    finally:
        session.close()

    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
