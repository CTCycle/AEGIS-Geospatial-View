from __future__ import annotations

from alembic import context
from sqlalchemy.engine import Connection

from server.configurations import get_server_settings
from server.repositories.database.engine import build_engine
from server.repositories.schemas import Base

config = context.config

target_metadata = Base.metadata


###############################################################################
def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


###############################################################################
def _include_object(
    object_: object,
    name: str | None,
    object_type: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    del object_, reflected, compare_to
    return not (object_type == "table" and name == "alembic_version")


###############################################################################
def run_migrations_offline() -> None:
    settings = get_server_settings()
    engine = build_engine(settings.database)
    try:
        context.configure(
            url=str(engine.url),
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        engine.dispose()


###############################################################################
def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_migrations(connection)
        return

    settings = get_server_settings()
    connectable = build_engine(settings.database)
    try:
        with connectable.connect() as connection:
            _run_migrations(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
