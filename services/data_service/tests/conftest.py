"""Shared pytest fixtures: an in-memory SQLite session with every table from
`models.py`.

The `tasks` table's `open_key` GENERATED column uses MySQL-only functions
(`IF`, `CONCAT`) that SQLite's generated-column support doesn't recognize —
SQLite validates the function names at `CREATE TABLE` time, so
`Base.metadata.create_all` fails outright for that one table. For tests,
`tasks` is created via hand-written SQLite DDL with a plain nullable
`open_key` column and no generated expression or unique index; "one open
task per key" is a MySQL-only constraint in this codebase and is not
exercised by these tests — see `services/data_service/ASSUMPTIONS.md`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.data_service.models import Base

_TASKS_DDL = """
CREATE TABLE tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id VARCHAR(16) NOT NULL,
    program_id VARCHAR(40) NOT NULL,
    specialty VARCHAR(40) NOT NULL,
    task_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    due_date DATE,
    snooze_until DATE,
    resolution VARCHAR(40),
    assigned_to VARCHAR(64),
    program_version INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    open_key VARCHAR(80)
)
"""


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    other_tables = [t for t in Base.metadata.sorted_tables if t.name != "tasks"]
    Base.metadata.create_all(engine, tables=other_tables)
    with engine.begin() as conn:
        conn.exec_driver_sql(_TASKS_DDL)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
