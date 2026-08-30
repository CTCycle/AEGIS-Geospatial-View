from __future__ import annotations

import shutil
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from filelock import FileLock, Timeout
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

from server.common.logger import logger
from server.repositories.database.sqlite import SQLiteRepository

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"
ALEMBIC_VERSION_TABLE = "alembic_version"


###############################################################################
class DatabaseMigrationError(RuntimeError):
    """Raised when the application cannot safely synchronize its schema."""


###############################################################################
@dataclass(frozen=True)
class MigrationResult:
    current_revisions: tuple[str, ...]
    head_revisions: tuple[str, ...]
    final_revisions: tuple[str, ...]
    fresh_database: bool
    migrations_applied: bool


###############################################################################
def synchronize_database(
    database: SQLiteRepository,
    *,
    on_ready: Callable[[], None] | None = None,
) -> MigrationResult:
    """Synchronize SQLite and run the optional callback under the file lock."""

    database_path = Path(database.db_path)
    original_exists = database_path.exists()
    timeout_seconds = migration_lock_timeout(database)
    lock = FileLock(str(database_path) + ".migration.lock")

    try:
        with lock.acquire(timeout=timeout_seconds):
            backup_path = _create_sqlite_backup(database, database_path)
            try:
                result = _synchronize_locked(database.engine)
                if on_ready is not None:
                    on_ready()
                if backup_path is not None:
                    backup_path.unlink(missing_ok=True)
                logger.info(
                    "SQLite synchronization complete: path=%s, revisions=%s",
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


###############################################################################
def _synchronize_locked(engine: Engine) -> MigrationResult:
    with engine.connect() as connection:
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
            "SQLite migration check: current=%s, head=%s",
            ",".join(current) or "base",
            ",".join(heads),
        )
        _validate_current_revisions(script, current)

        table_names = set(inspect(connection).get_table_names())
        application_tables = table_names - {ALEMBIC_VERSION_TABLE}
        fresh_database = not application_tables

        if not current and not fresh_database:
            raise DatabaseMigrationError(
                "Existing non-empty SQLite database has no alembic_version table "
                "revision. Back up the database, migrate or rebuild it explicitly, "
                "then run AEGIS again."
            )

        if current != heads:
            logger.info("Applying pending SQLite migrations to head %s.", heads[0])
            _run_alembic_command(
                config,
                connection,
                lambda cfg: command.upgrade(cfg, "head"),
            )

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
            migrations_applied=current != final,
        )


###############################################################################
def _alembic_config() -> Config:
    if not ALEMBIC_CONFIG_PATH.is_file():
        raise DatabaseMigrationError(
            f"Alembic configuration was not found at {ALEMBIC_CONFIG_PATH}."
        )
    return Config(str(ALEMBIC_CONFIG_PATH))


###############################################################################
def _run_alembic_command(
    config: Config,
    connection: Connection,
    operation: Callable[[Config], None],
) -> None:
    config.attributes["connection"] = connection
    operation(config)
    # SQLite DDL and the Alembic version-table write use the shared connection.
    # Commit before the migration connection is returned to the pool.
    connection.commit()


###############################################################################
def _current_revisions(connection: Connection) -> tuple[str, ...]:
    context = MigrationContext.configure(connection)
    return tuple(context.get_current_heads())


###############################################################################
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


###############################################################################
def migration_lock_timeout(database: SQLiteRepository) -> int:
    return max(1, int(database.settings.sqlite_lock_timeout_seconds))


###############################################################################
def _create_sqlite_backup(
    database: SQLiteRepository,
    database_path: Path,
) -> Path | None:
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


###############################################################################
def _restore_sqlite_backup(
    database: SQLiteRepository,
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
        logger.error(
            "Restored SQLite database from migration backup: %s", database_path
        )
    elif not original_exists:
        database_path.unlink(missing_ok=True)
        logger.error(
            "Removed incomplete SQLite database after migration failure: %s",
            database_path,
        )
