from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from server.configurations import DatabaseSettings

SQLITE_BUSY_TIMEOUT_MS = 5000


###############################################################################
def configure_sqlite_connection(dbapi_connection: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


###############################################################################
def build_engine(settings: DatabaseSettings) -> Engine:
    database_path = Path(settings.database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    def on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        configure_sqlite_connection(dbapi_connection)

    event.listen(engine, "connect", on_connect)
    return engine


###############################################################################
def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
