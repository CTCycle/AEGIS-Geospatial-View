from __future__ import annotations

from unittest.mock import patch

from server.configurations import DatabaseSettings
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository


def test_sqlite_runtime_does_not_create_schema(tmp_path) -> None:
    settings = DatabaseSettings(
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
    with patch(
        "server.repositories.database.sqlite.Base.metadata.create_all"
    ) as create_all:
        _ = SQLiteRepository(settings)
    create_all.assert_not_called()


def test_postgres_runtime_does_not_create_schema() -> None:
    settings = DatabaseSettings(
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
    with patch(
        "server.repositories.database.postgres.sqlalchemy.create_engine"
    ) as create_engine:
        create_engine.return_value = object()
        with patch(
            "server.repositories.database.postgres.sessionmaker"
        ) as sessionmaker:
            _ = PostgresRepository(settings)
    sessionmaker.assert_called_once()
