from __future__ import annotations

from types import SimpleNamespace

from server.configurations import DatabaseSettings
from server.repositories.database.backend import build_database_backend
from server.repositories.database.initializer import initialize_database

###############################################################################
def _settings(*, embedded_database: bool, database_path: str) -> DatabaseSettings:
    return DatabaseSettings(
        database_path=database_path,
        embedded_database=embedded_database,
        engine=None if embedded_database else "postgresql+psycopg",
        host=None if embedded_database else "localhost",
        port=None if embedded_database else 5432,
        database_name=None if embedded_database else "aegis",
        username=None if embedded_database else "postgres",
        password=None if embedded_database else "postgres",
        ssl=False,
        ssl_ca=None,
        connect_timeout=10,
        insert_batch_size=100,
    )

###############################################################################
def test_initialize_database_uses_only_the_injected_backend(monkeypatch) -> None:
    calls: list[object] = []
    backend = SimpleNamespace(engine=object())
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: calls.append(engine),
    )

    initialize_database(backend)  # type: ignore[arg-type]

    assert calls == [backend.engine]

###############################################################################
def test_database_factory_selects_sqlite_without_initializing_schema(monkeypatch) -> None:
    settings = _settings(embedded_database=True, database_path="test.db")
    created: list[DatabaseSettings] = []
    repository = SimpleNamespace(engine=object(), session=object(), db_path="test.db")
    monkeypatch.setattr(
        "server.repositories.database.backend.SQLiteRepository",
        lambda received: created.append(received) or repository,
    )

    result = build_database_backend(settings)

    assert result is repository
    assert created == [settings]

###############################################################################
def test_database_factory_selects_postgres_without_initializing_schema(monkeypatch) -> None:
    settings = _settings(embedded_database=False, database_path="unused.db")
    repository = SimpleNamespace(engine=object(), session=object(), db_path=None)
    monkeypatch.setattr(
        "server.repositories.database.backend.PostgresRepository",
        lambda received: repository,
    )

    assert build_database_backend(settings) is repository
