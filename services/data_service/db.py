"""Engine/session factory for the Data Service.

One process-wide `Engine`, one `sessionmaker`. Repository functions never
create their own session — they take a `Session` argument — so tests can
hand them a SQLite session directly instead of a live MySQL connection.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from libs.common.errors import VersionConflictError
from libs.common.settings import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _session_factory


def maybe_for_update(query, session: Session):
    """`SELECT ... FOR UPDATE` on MySQL so concurrent writers to the same row
    serialize instead of racing on a stale read; skipped on SQLite, which
    doesn't support it and is only ever used single-threaded in tests."""
    if session.get_bind().dialect.name == "sqlite":
        return query
    return query.with_for_update()


@contextmanager
def session_scope() -> Iterator[Session]:
    """One transaction per `with` block: commit on success, rollback on error.

    Every state-changing RPC uses exactly one of these, so the state change,
    the audit row and the outbox row land in the same transaction.

    The plan's `uq_one_open_task` unique index is the actual enforcement of
    "one open task per patient/program/specialty" (MySQL has no partial
    indexes, so it can't be a WHERE-guarded constraint) — application code
    already avoids tripping it in the one place that inserts a `Task`
    (`save_evaluation_result` serializes per patient via a `patient_eval_state`
    row lock before deciding whether to create one), but a raw
    `IntegrityError` from that index is still translated into a clean
    `VersionConflictError` here as a safety net, rather than leaking a MySQL
    error to the gRPC caller.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_one_open_task" in str(exc.orig):
            raise VersionConflictError(
                "an open task already exists for this patient/program/specialty"
            ) from exc
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
