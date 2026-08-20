from __future__ import annotations

import shutil
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from filelock import FileLock, Timeout
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from server.common.logger import logger
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.schemas import Base

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"
INITIAL_REVISION = "202608200001"
ALEMBIC_VERSION_TABLE = "alembic_version"
POSTGRES_LOCK_KEY = "aegis-schema-migrations"


class DatabaseMigrationError(RuntimeError):
    """Raised when the application cannot safely synchronize its schema."""


@dataclass(frozen=True)
class MigrationResult:
    current_revisions: tuple[str, ...]
    head_revisions: tuple[str, ...]
    final_revisions: tuple[str, ...]
    fresh_database: bool
    adopted_legacy_schema: bool
    migrations_applied: bool


def synchronize_database(
    database: DatabaseBackend,
    *,
    on_ready: Callable[[], None] | None = None,
) -> MigrationResult:
    """Synchronize a database and run the optional post-migration callback.

    The callback runs while the migration lock is held.  This is used for the
    application's idempotent seeders so two first-start processes cannot seed
    the same database concurrently.
    """

    if database.db_path is not None:
        return _synchronize_sqlite(database, on_ready=on_ready)
    return _synchronize_postgres(database, on_ready=on_ready)


def _synchronize_sqlite(
    database: DatabaseBackend,
    *,
    on_ready: Callable[[], None] | None,
) -> MigrationResult:
    database_path = Path(database.db_path or "")
    original_exists = database_path.exists()
    timeout_seconds = migration_lock_timeout(database)
    lock = FileLock(str(database_path) + ".migration.lock")

    try:
        with lock.acquire(timeout=timeout_seconds):
            backup_path = _create_sqlite_backup(database, database_path)
            try:
                result = _synchronize_locked(database.engine, database)
                if on_ready is not None:
                    on_ready()
                _assert_at_head(database.engine)
                if backup_path is not None:
                    backup_path.unlink(missing_ok=True)
                logger.info(
                    "Database synchronization complete: sqlite=%s, revisions=%s",
                    database_path,
                    ",".join(result.final_revisions) or "base",
                )
                return result
            except BaseException:
                _restore_sqlite_backup(
                    database,
                    database_path,
                    backup_path,
                    original_exists=original_exists,
                )
                raise
    except Timeout as exc:
        raise DatabaseMigrationError(
            f"Timed out after {timeout_seconds}s waiting for the SQLite migration lock "
            f"at {lock.lock_file}."
        ) from exc


def _synchronize_postgres(
    database: DatabaseBackend,
    *,
    on_ready: Callable[[], None] | None,
) -> MigrationResult:
    timeout_seconds = migration_lock_timeout(database)
    with database.engine.connect() as connection:
        acquire_postgres_lock(connection, timeout_seconds)
        try:
            result = _synchronize_locked(database.engine, database, connection)
            if on_ready is not None:
                on_ready()
            _assert_at_head(database.engine)
            logger.info(
                "Database synchronization complete: PostgreSQL revisions=%s",
                ",".join(result.final_revisions) or "base",
            )
            return result
        finally:
            release_postgres_lock(connection)


def _synchronize_locked(
    engine: Engine,
    database: DatabaseBackend,
    connection: Connection | None = None,
) -> MigrationResult:
    if connection is None:
        with engine.connect() as owned_connection:
            return _synchronize_locked(engine, database, owned_connection)

    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    heads = tuple(script.get_heads())
    if len(heads) != 1:
        raise DatabaseMigrationError(
            "The Alembic migration tree must have exactly one head; "
            f"found {', '.join(heads) or 'none'}."
        )

    current = _current_revisions(connection)
    logger.info(
        "Database migration check: current=%s, head=%s",
        ",".join(current) or "base",
        ",".join(heads),
    )
    _validate_current_revisions(script, current)

    table_names = set(inspect(connection).get_table_names())
    application_tables = table_names - {ALEMBIC_VERSION_TABLE}
    fresh_database = not application_tables
    adopted_legacy_schema = False

    if not current:
        if fresh_database:
            logger.info("Applying initial Alembic schema to an empty database.")
        else:
            _verify_legacy_schema(connection, script)
            _stamp_initial_revision(config, connection)
            adopted_legacy_schema = True
            logger.info(
                "Adopted verified pre-Alembic schema at revision %s.", INITIAL_REVISION
            )

    if current != heads:
        logger.info("Applying pending Alembic migrations to head %s.", heads[0])
        _run_alembic_command(config, connection, lambda cfg: command.upgrade(cfg, "head"))

    final = _current_revisions(connection)
    if set(final) != set(heads):
        raise DatabaseMigrationError(
            "Alembic completed without reaching the expected head: "
            f"current={final!r}, expected={heads!r}."
        )

    return MigrationResult(
        current_revisions=current,
        head_revisions=heads,
        final_revisions=final,
        fresh_database=fresh_database,
        adopted_legacy_schema=adopted_legacy_schema,
        migrations_applied=current != final or adopted_legacy_schema,
    )


def _alembic_config() -> Config:
    if not ALEMBIC_CONFIG_PATH.is_file():
        raise DatabaseMigrationError(
            f"Alembic configuration was not found at {ALEMBIC_CONFIG_PATH}."
        )
    return Config(str(ALEMBIC_CONFIG_PATH))


def _run_alembic_command(
    config: Config,
    connection: Connection,
    operation: Callable[[Config], None],
) -> None:
    config.attributes["connection"] = connection
    operation(config)
    # SQLite's dialect uses non-transactional DDL.  The version-table writes
    # still participate in SQLAlchemy 2.x autobegin, so explicitly commit the
    # shared connection before a second connection checks the resulting head.
    connection.commit()


def _stamp_initial_revision(config: Config, connection: Connection) -> None:
    script = ScriptDirectory.from_config(config)
    try:
        script.get_revision(INITIAL_REVISION)
    except CommandError as exc:
        raise DatabaseMigrationError(
            f"The legacy adoption revision {INITIAL_REVISION} is missing."
        ) from exc
    _run_alembic_command(
        config,
        connection,
        lambda cfg: command.stamp(cfg, INITIAL_REVISION),
    )


def _current_revisions(connection: Connection) -> tuple[str, ...]:
    context = MigrationContext.configure(connection)
    return tuple(context.get_current_heads())


def _assert_at_head(engine: Engine) -> None:
    with engine.connect() as connection:
        config = _alembic_config()
        script = ScriptDirectory.from_config(config)
        current = set(_current_revisions(connection))
        heads = set(script.get_heads())
        if current != heads:
            raise DatabaseMigrationError(
                f"Database is not at Alembic head: current={sorted(current)!r}, "
                f"head={sorted(heads)!r}."
            )


def _validate_current_revisions(
    script: ScriptDirectory,
    current: tuple[str, ...],
) -> None:
    for revision in current:
        try:
            script.get_revision(revision)
        except CommandError as exc:
            raise DatabaseMigrationError(
                f"Database references unknown Alembic revision {revision!r}."
            ) from exc


def _verify_legacy_schema(connection: Connection, script: ScriptDirectory) -> None:
    if script.get_heads() != [INITIAL_REVISION]:
        raise DatabaseMigrationError(
            "An unversioned non-empty database can only be adopted while the "
            "initial Alembic revision is the sole head. Stamp a reviewed legacy "
            "database manually before applying later migration revisions."
        )

    migration_context = MigrationContext.configure(
        connection,
        opts={
            "target_metadata": Base.metadata,
            "compare_type": True,
            "compare_server_default": True,
            "include_object": _include_object,
            "render_as_batch": connection.dialect.name == "sqlite",
        },
    )
    differences = compare_metadata(migration_context, Base.metadata)
    if differences:
        preview = "; ".join(repr(item) for item in differences[:6])
        suffix = "" if len(differences) <= 6 else f"; ... ({len(differences)} total)"
        raise DatabaseMigrationError(
            "Existing database schema does not match the pre-Alembic baseline: "
            f"{preview}{suffix}"
        )


def _include_object(
    object_: object,
    name: str | None,
    object_type: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    del object_, reflected, compare_to
    return not (object_type == "table" and name == ALEMBIC_VERSION_TABLE)


def migration_lock_timeout(database: DatabaseBackend) -> int:
    settings = getattr(database, "settings", None)
    value = getattr(settings, "database_migration_lock_timeout_seconds", 60)
    return max(1, int(value))


def _create_sqlite_backup(database: DatabaseBackend, database_path: Path) -> Path | None:
    if not database_path.exists():
        return None

    backup_path = database_path.with_name(
        f"{database_path.name}.migration-backup-{uuid.uuid4().hex}.db"
    )
    database.engine.dispose()
    source: sqlite3.Connection | None = None
    target: sqlite3.Connection | None = None
    try:
        source = sqlite3.connect(str(database_path))
        target = sqlite3.connect(str(backup_path))
        source.backup(target)
        target.commit()
        logger.info("Created SQLite migration backup: %s", backup_path)
        return backup_path
    except BaseException:
        backup_path.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            source.close()
        if target is not None:
            target.close()


def _restore_sqlite_backup(
    database: DatabaseBackend,
    database_path: Path,
    backup_path: Path | None,
    *,
    original_exists: bool,
) -> None:
    database.engine.dispose()
    for sidecar in (
        database_path.with_name(database_path.name + "-wal"),
        database_path.with_name(database_path.name + "-shm"),
    ):
        sidecar.unlink(missing_ok=True)

    if backup_path is not None and backup_path.exists():
        shutil.copy2(backup_path, database_path)
        backup_path.unlink(missing_ok=True)
        logger.error("Restored SQLite database from migration backup: %s", database_path)
    elif not original_exists:
        database_path.unlink(missing_ok=True)
        logger.error("Removed incomplete SQLite database after migration failure: %s", database_path)


def acquire_postgres_lock(connection: Connection, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        acquired = bool(
            connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
                {"lock_key": POSTGRES_LOCK_KEY},
            )
        )
        connection.commit()
        if acquired:
            logger.info("Acquired PostgreSQL migration advisory lock.")
            return
        if time.monotonic() >= deadline:
            raise DatabaseMigrationError(
                f"Timed out after {timeout_seconds}s waiting for the PostgreSQL "
                "migration advisory lock."
            )
        time.sleep(0.25)


def release_postgres_lock(connection: Connection) -> None:
    try:
        connection.scalar(
            text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
            {"lock_key": POSTGRES_LOCK_KEY},
        )
        connection.commit()
        logger.info("Released PostgreSQL migration advisory lock.")
    except Exception:
        logger.exception("Failed to release PostgreSQL migration advisory lock.")
