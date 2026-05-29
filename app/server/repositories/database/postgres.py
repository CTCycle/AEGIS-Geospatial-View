from __future__ import annotations

import urllib.parse
from typing import Any

import sqlalchemy
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from server.configurations import DatabaseSettings
from server.repositories.database.orm_table_operations import SqlAlchemyTableOperationsMixin


###############################################################################
class PostgresRepository(SqlAlchemyTableOperationsMixin):
    warn_on_missing_table = False

    def __init__(self, settings: DatabaseSettings) -> None:
        if not settings.host:
            raise ValueError("Database host must be provided for external database.")
        if not settings.database_name:
            raise ValueError("Database name must be provided for external database.")
        if not settings.username:
            raise ValueError(
                "Database username must be provided for external database."
            )

        port = settings.port or 5432
        engine_name = settings.engine
        if engine_name != "postgresql+psycopg":
            raise ValueError(f"Unsupported database engine: {settings.engine}")
        password = settings.password or ""
        connect_args: dict[str, Any] = {"connect_timeout": settings.connect_timeout}
        if settings.ssl:
            connect_args["sslmode"] = "require"
            if settings.ssl_ca:
                connect_args["sslrootcert"] = settings.ssl_ca

        safe_username = urllib.parse.quote_plus(settings.username)
        safe_password = urllib.parse.quote_plus(password)
        self.db_path: str | None = None
        self.engine: Engine = sqlalchemy.create_engine(
            f"{engine_name}://{safe_username}:{safe_password}@{settings.host}:{port}/{settings.database_name}",
            echo=False,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.session = self.session_factory
        self.insert_batch_size = settings.insert_batch_size

    # -------------------------------------------------------------------------
    def _insert_statement(self, table_cls: type[Any], records: list[dict[str, object]]) -> Any:
        return postgres_insert(table_cls).values(records)
