from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from server.repositories.database.engine import configure_sqlite_connection
from server.repositories.database.sqlite import SQLiteRepository
from server.configurations import DatabaseSettings

###############################################################################
class _Cursor:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.statements: list[str] = []

    # -------------------------------------------------------------------------
    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    # -------------------------------------------------------------------------
    def close(self) -> None:
        return None

###############################################################################
class _Connection:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    # -------------------------------------------------------------------------
    def cursor(self) -> _Cursor:
        return self.cursor_instance

###############################################################################
def test_sqlite_connection_listener_applies_expected_pragmas() -> None:
    connection = _Connection()

    configure_sqlite_connection(connection)

    assert connection.cursor_instance.statements == [
        "PRAGMA foreign_keys=ON",
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=5000",
        "PRAGMA synchronous=NORMAL",
    ]


###############################################################################
def test_sqlite_engine_applies_pragmas_to_live_connections(tmp_path: Path) -> None:
    repository = SQLiteRepository(
        DatabaseSettings(database_path=str(tmp_path / "database.db"))
    )

    with repository.engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
        assert connection.scalar(text("PRAGMA synchronous")) == 1

    repository.engine.dispose()
