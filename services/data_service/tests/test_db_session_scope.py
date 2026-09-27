"""`session_scope`'s translation of the `uq_one_open_task` unique-index
violation into a clean `VersionConflictError` — a fake session raising the
IntegrityError MySQL would raise, so this doesn't need a real MySQL server.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from libs.common.errors import VersionConflictError
from services.data_service import db as db_module


class _FakeSessionThatConflictsOnCommit:
    def commit(self):
        # Shape of a real PyMySQL duplicate-key error for this index.
        msg = "(1062, \"Duplicate entry 'P1|prog|spec' for key 'tasks.uq_one_open_task'\")"
        raise IntegrityError("UPDATE tasks ...", {}, Exception(msg))

    def rollback(self):
        pass

    def close(self):
        pass


class _FakeSessionThatConflictsOnSomeOtherConstraint:
    def commit(self):
        msg = "(1452, \"Cannot add or update a child row: a foreign key constraint fails\")"
        raise IntegrityError("INSERT ...", {}, Exception(msg))

    def rollback(self):
        pass

    def close(self):
        pass


def test_one_open_task_conflict_becomes_a_clean_version_conflict_error(monkeypatch):
    monkeypatch.setattr(db_module, "get_session_factory", lambda: _FakeSessionThatConflictsOnCommit)
    with pytest.raises(VersionConflictError):
        with db_module.session_scope():
            pass


def test_other_integrity_errors_are_not_swallowed(monkeypatch):
    fake_cls = _FakeSessionThatConflictsOnSomeOtherConstraint
    monkeypatch.setattr(db_module, "get_session_factory", lambda: fake_cls)
    with pytest.raises(IntegrityError):
        with db_module.session_scope():
            pass
