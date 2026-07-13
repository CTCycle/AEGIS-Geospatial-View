from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from server.configurations import DatabaseSettings


###############################################################################
def build_engine(settings: DatabaseSettings) -> Engine:
    if settings.embedded_database:
        engine = create_engine(
            f"sqlite:///{settings.database_path}",
            future=True,
            connect_args={
                "check_same_thread": False,
                "timeout": settings.sqlite_busy_timeout_ms / 1000,
            },
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if settings.sqlite_wal_enabled:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        return engine

    if not settings.host or not settings.database_name or not settings.username:
        raise ValueError("External database host, name, and username are required.")
    url = f"{settings.engine}://{settings.username}:{settings.password or ''}@{settings.host}:{settings.port or 5432}/{settings.database_name}"
    return create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle_seconds,
        connect_args={"connect_timeout": settings.connect_timeout},
    )


###############################################################################
def build_session_factory(engine: Engine):
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
