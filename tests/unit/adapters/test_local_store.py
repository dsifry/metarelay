"""Tests for SQLite local event store."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from metarelay.adapters.local_store import SqliteEventStore
from metarelay.core.models import Event, HandlerResult, HandlerResultStatus


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    """Return a temp database path."""
    return str(tmp_path / "test.db")


@pytest.fixture()
def store(db_path: str) -> SqliteEventStore:
    """Create a test event store."""
    return SqliteEventStore(db_path)


def make_event(
    id: int = 1,
    repo: str = "owner/repo",
    event_type: str = "check_run",
    action: str = "completed",
) -> Event:
    """Create a test event."""
    return Event(
        id=id,
        repo=repo,
        event_type=event_type,
        action=action,
        summary="Test event",
    )


def make_result(
    handler_name: str = "test-handler",
    status: HandlerResultStatus = HandlerResultStatus.SUCCESS,
) -> HandlerResult:
    """Create a test handler result."""
    return HandlerResult(handler_name=handler_name, status=status)


class TestCursorOperations:
    """Tests for cursor get/set."""

    def test_get_cursor_returns_none_initially(self, store: SqliteEventStore) -> None:
        assert store.get_cursor("owner/repo") is None

    def test_set_and_get_cursor(self, store: SqliteEventStore) -> None:
        store.set_cursor("owner/repo", 42)
        cursor = store.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.repo == "owner/repo"
        assert cursor.last_event_id == 42

    def test_set_cursor_updates_existing(self, store: SqliteEventStore) -> None:
        store.set_cursor("owner/repo", 10)
        store.set_cursor("owner/repo", 20)
        cursor = store.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.last_event_id == 20

    def test_cursors_are_per_repo(self, store: SqliteEventStore) -> None:
        store.set_cursor("org/repo1", 10)
        store.set_cursor("org/repo2", 20)
        c1 = store.get_cursor("org/repo1")
        c2 = store.get_cursor("org/repo2")
        assert c1 is not None
        assert c2 is not None
        assert c1.last_event_id == 10
        assert c2.last_event_id == 20


class TestEventLogging:
    """Tests for event logging and dedup."""

    def test_log_event(self, store: SqliteEventStore) -> None:
        event = make_event(id=1)
        result = make_result()
        store.log_event(event, result)
        assert store.has_event(1)

    def test_has_event_false_for_unknown(self, store: SqliteEventStore) -> None:
        assert not store.has_event(999)

    def test_duplicate_event_ignored(self, store: SqliteEventStore) -> None:
        event = make_event(id=1)
        result = make_result()
        store.log_event(event, result)
        # Second log of same event should not raise
        store.log_event(event, result)
        assert store.has_event(1)

    def test_multiple_events_logged(self, store: SqliteEventStore) -> None:
        for i in range(1, 4):
            store.log_event(make_event(id=i), make_result())
        assert store.has_event(1)
        assert store.has_event(2)
        assert store.has_event(3)
        assert not store.has_event(4)


class TestSecurePermissions:
    """Tests for secure file permissions."""

    def test_creates_directory_with_0700(self, tmp_path: Path) -> None:
        db_dir = tmp_path / "subdir" / "nested"
        db_path = str(db_dir / "test.db")
        SqliteEventStore(db_path)

        mode = stat.S_IMODE(db_dir.stat().st_mode)
        assert mode == 0o700

    def test_creates_file_with_0600(self, db_path: str) -> None:
        SqliteEventStore(db_path)
        path = Path(db_path)
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600

    def test_fixes_permissive_file_permissions(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        db_file.touch(mode=0o644)

        with pytest.warns(UserWarning, match="permissive permissions"):
            SqliteEventStore(str(db_file))

        mode = stat.S_IMODE(db_file.stat().st_mode)
        assert mode == 0o600

    def test_close_and_reopen(self, db_path: str) -> None:
        store = SqliteEventStore(db_path)
        store.set_cursor("owner/repo", 42)
        store.close()

        store2 = SqliteEventStore(db_path)
        cursor = store2.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.last_event_id == 42
