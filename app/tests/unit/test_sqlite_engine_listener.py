from __future__ import annotations

from server.configurations import DatabaseSettings
from server.repositories.database.engine import configure_sqlite_connection


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_instance


def test_sqlite_connection_listener_applies_expected_pragmas() -> None:
    settings = DatabaseSettings(
        database_path="test.db",
        embedded_database=True,
        engine=None,
        host=None,
        port=None,
        database_name=None,
        username=None,
        password=None,
        ssl=False,
        ssl_ca=None,
        connect_timeout=10,
        insert_batch_size=100,
        sqlite_busy_timeout_ms=3210,
        sqlite_wal_enabled=True,
    )
    connection = _Connection()

    configure_sqlite_connection(connection, settings)

    assert connection.cursor_instance.statements == [
        "PRAGMA foreign_keys=ON",
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=3210",
        "PRAGMA synchronous=NORMAL",
    ]
