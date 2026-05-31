from __future__ import annotations

from server.configurations import DatabaseSettings
from server.repositories.database.initializer import initialize_database


def test_initialize_database_ensures_sqlite_schema(monkeypatch, tmp_path) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "database.db"),
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
    )
    created: list[object] = []

    class _Repository:
        def __init__(self, passed_settings: DatabaseSettings) -> None:
            self.engine = object()
            self.db_path = passed_settings.database_path
            created.append(self.engine)

    monkeypatch.setattr(
        "server.repositories.database.initializer.SQLiteRepository",
        _Repository,
    )
    calls: list[object] = []
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: calls.append(engine),
    )

    initialize_database(settings)

    assert calls == created


def test_initialize_database_uses_passed_database_settings(
    monkeypatch, tmp_path
) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "custom.db"),
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
        insert_batch_size=250,
    )
    received: list[DatabaseSettings] = []

    class _Repository:
        def __init__(self, passed_settings: DatabaseSettings) -> None:
            received.append(passed_settings)
            self.engine = object()
            self.db_path = passed_settings.database_path

    monkeypatch.setattr(
        "server.repositories.database.initializer.SQLiteRepository",
        _Repository,
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: None,
    )

    initialize_database(settings)

    assert received == [settings]


def test_initialize_database_defaults_to_server_settings(
    monkeypatch, tmp_path
) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "default.db"),
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
        insert_batch_size=400,
    )
    received: list[DatabaseSettings] = []

    class _Repository:
        def __init__(self, passed_settings: DatabaseSettings) -> None:
            received.append(passed_settings)
            self.engine = object()
            self.db_path = passed_settings.database_path

    monkeypatch.setattr(
        "server.repositories.database.initializer.get_server_settings",
        lambda: type("Settings", (), {"database": settings})(),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.SQLiteRepository",
        _Repository,
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: None,
    )

    initialize_database()

    assert received == [settings]


def test_initialize_database_ensures_postgres_schema_when_external_mode(
    monkeypatch, tmp_path
) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "database.db"),
        embedded_database=False,
        engine="postgresql+psycopg",
        host="localhost",
        port=5432,
        database_name="aegis",
        username="postgres",
        password="postgres",
        ssl=False,
        ssl_ca=None,
        connect_timeout=10,
        insert_batch_size=100,
    )

    monkeypatch.setattr(
        "server.repositories.database.initializer.PostgresRepository",
        lambda passed_settings: type(
            "Repository",
            (),
            {"engine": object(), "db_path": passed_settings.database_path},
        )(),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: None,
    )

    initialize_database(settings)

    assert "server.repositories.database.postgres" in __import__("sys").modules
