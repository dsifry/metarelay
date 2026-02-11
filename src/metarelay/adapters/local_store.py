"""SQLite-based local event store for cursor tracking and event dedup.

Security features:
- Database directory created with 0700 permissions (owner only)
- Database file created with 0600 permissions (owner read/write only)
- Existing permissive permissions are fixed with a warning
"""

from __future__ import annotations

import sqlite3
import stat
import warnings
from pathlib import Path

from metarelay.core.errors import EventStoreError
from metarelay.core.interfaces import EventStorePort
from metarelay.core.models import CursorPosition, Event, HandlerResult

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS cursor (
    repo TEXT PRIMARY KEY,
    last_event_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    remote_id INTEGER NOT NULL UNIQUE,
    repo TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action TEXT NOT NULL,
    summary TEXT,
    handler_name TEXT,
    handler_result TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_event_log_repo ON event_log(repo);
CREATE INDEX IF NOT EXISTS idx_event_log_remote_id ON event_log(remote_id);
"""


class SqliteEventStore(EventStorePort):
    """SQLite-based event store implementing EventStorePort.

    Provides cursor tracking per repo and event deduplication via
    the event_log table's UNIQUE constraint on remote_id.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None
        self._ensure_secure_path()
        self._init_database()

    def _ensure_secure_path(self) -> None:
        """Ensure database directory and file have secure permissions."""
        path = Path(self.db_path)
        db_dir = path.parent

        if not db_dir.exists():
            db_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        else:
            current_mode = stat.S_IMODE(db_dir.stat().st_mode)
            if current_mode != 0o700:
                db_dir.chmod(0o700)

        if path.exists():
            current_mode = stat.S_IMODE(path.stat().st_mode)
            if current_mode & (stat.S_IRWXG | stat.S_IRWXO):
                warnings.warn(
                    f"Database file {self.db_path} had permissive permissions "
                    f"({oct(current_mode)}). Fixing to 0600.",
                    UserWarning,
                    stacklevel=2,
                )
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def _init_database(self) -> None:
        """Initialize database schema and set file permissions."""
        conn = self._get_connection()
        conn.executescript(_CREATE_TABLES_SQL)
        conn.commit()

        # File is guaranteed to exist after executescript creates/opens the DB
        Path(self.db_path).chmod(stat.S_IRUSR | stat.S_IWUSR)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(self.db_path)
                self._connection.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                raise EventStoreError(f"Failed to connect to database: {e}") from e
        return self._connection

    def get_cursor(self, repo: str) -> CursorPosition | None:
        """Get the current cursor position for a repo."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT repo, last_event_id, updated_at FROM cursor WHERE repo = ?",
            (repo,),
        ).fetchone()

        if row is None:
            return None

        return CursorPosition(
            repo=row["repo"],
            last_event_id=row["last_event_id"],
        )

    def set_cursor(self, repo: str, last_event_id: int) -> None:
        """Update the cursor position for a repo."""
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO cursor (repo, last_event_id, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(repo) DO UPDATE SET
                last_event_id = excluded.last_event_id,
                updated_at = excluded.updated_at
            """,
            (repo, last_event_id),
        )
        conn.commit()

    def log_event(self, event: Event, result: HandlerResult) -> None:
        """Log a processed event and its handler result."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO event_log (
                    remote_id, repo, event_type, action,
                    summary, handler_name, handler_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.repo,
                    event.event_type,
                    event.action,
                    event.summary,
                    result.handler_name,
                    result.status.value,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicate remote_id — already logged, ignore
            pass

    def has_event(self, remote_id: int) -> bool:
        """Check if an event has already been processed."""
        conn = self._get_connection()
        row = conn.execute("SELECT 1 FROM event_log WHERE remote_id = ?", (remote_id,)).fetchone()
        return row is not None

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __del__(self) -> None:
        """Ensure connection is closed on garbage collection."""
        self.close()
