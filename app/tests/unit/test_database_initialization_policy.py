from __future__ import annotations

from pathlib import Path

import pytest
from filelock import Timeout
from sqlalchemy import inspect

from server.configurations import DatabaseSettings
from server.repositories.database import migration_runner
from server.repositories.database.initializer import initialize_database
from server.repositories.database.migration_runner import DatabaseMigrationError
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import (
    Base,
    CredentialEncryptionMaterial,
    ReferenceCountryRecord,
)
from server.repositories.schemas.models import (
    ApplicationRuntimeSettingsRecord,
    ConversationRecord,
)
from server.repositories.model_settings import ModelSettingsRepository
from server.repositories.schemas.models import ModelProviderSettingsRecord
from server.services.catalog.startup import seed_reference_catalog

###############################################################################
def _settings(database_path: Path, *, timeout: int = 60) -> DatabaseSettings:
    return DatabaseSettings(
        database_path=str(database_path),
        sqlite_lock_timeout_seconds=timeout,
    )

###############################################################################
def _initialize(repository: SQLiteRepository):
    return initialize_database(
        repository,
        on_ready=lambda: seed_reference_catalog(repository),
    )

###############################################################################
def test_missing_sqlite_database_migrates_schema_and_seeds(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    repository = SQLiteRepository(_settings(database_path))

    result = _initialize(repository)

    assert result.fresh_database is True
    assert result.migrations_applied is True
    assert database_path.is_file()
    assert "alembic_version" in inspect(repository.engine).get_table_names()
    assert repository.count_records(CredentialEncryptionMaterial) == 1
    assert repository.count_records(ReferenceCountryRecord) > 0
    assert repository.count_records(ApplicationRuntimeSettingsRecord) == 1

###############################################################################
def test_existing_sqlite_database_is_idempotent(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "database.db"
    repository = SQLiteRepository(_settings(database_path))
    _initialize(repository)
    first_counts = (
        repository.count_records(CredentialEncryptionMaterial),
        repository.count_records(ReferenceCountryRecord),
    )
    repository.engine.dispose()

    monkeypatch.setattr(
        migration_runner,
        "_create_sqlite_backup",
        lambda *_args: pytest.fail("idempotent startup must not create a backup"),
    )
    second_repository = SQLiteRepository(_settings(database_path))
    result = _initialize(second_repository)

    assert result.migrations_applied is False
    assert (
        second_repository.count_records(CredentialEncryptionMaterial),
        second_repository.count_records(ReferenceCountryRecord),
    ) == first_counts

###############################################################################
def test_at_head_missing_required_seed_creates_backup_before_reseeding(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(database_path)
    repository = SQLiteRepository(settings)
    _initialize(repository)
    with repository.engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM model_provider_settings")
    repository.engine.dispose()

    original_backup = migration_runner._create_sqlite_backup
    backups: list[Path | None] = []

    def track_backup(database: SQLiteRepository, path: Path) -> Path | None:
        assert not ModelSettingsRepository(database).has_required()
        backup = original_backup(database, path)
        backups.append(backup)
        return backup

    monkeypatch.setattr(migration_runner, "_create_sqlite_backup", track_backup)
    repaired = SQLiteRepository(settings)

    result = _initialize(repaired)

    assert result.migrations_applied is False
    assert len(backups) == 1
    assert backups[0] is not None
    assert ModelSettingsRepository(repaired).has_required()
    assert repaired.count_records(ModelProviderSettingsRecord) == 1

###############################################################################
def test_populated_unversioned_sqlite_database_is_rejected_without_stamping(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(database_path)
    legacy_repository = SQLiteRepository(settings)
    Base.metadata.create_all(legacy_repository.engine)
    with legacy_repository.session() as session:
        session.add(ConversationRecord(id="unversioned-conversation", title="Keep me"))
        session.commit()
    legacy_repository.engine.dispose()

    with pytest.raises(DatabaseMigrationError, match="no alembic_version"):
        _initialize(SQLiteRepository(settings))

    verification_repository = SQLiteRepository(settings)
    assert (
        "alembic_version"
        not in inspect(verification_repository.engine).get_table_names()
    )
    assert verification_repository.count_records(ConversationRecord) == 1

###############################################################################
def test_unknown_revision_is_rejected_and_original_file_is_restored(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(database_path)
    repository = SQLiteRepository(settings)
    _initialize(repository)
    repository.engine.dispose()

    corrupt_repository = SQLiteRepository(settings)
    with corrupt_repository.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE alembic_version SET version_num = 'unknown-revision'"
        )
    corrupt_repository.engine.dispose()

    with pytest.raises(DatabaseMigrationError, match="unknown Alembic revision"):
        _initialize(SQLiteRepository(settings))

    verification_repository = SQLiteRepository(settings)
    with verification_repository.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    assert version == "unknown-revision"
    verification_repository.engine.dispose()

###############################################################################
def test_seeding_failure_restores_existing_sqlite_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(database_path)
    repository = SQLiteRepository(settings)
    _initialize(repository)
    with repository.engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM model_provider_settings")
    repository.engine.dispose()

    monkeypatch.setattr(
        "server.repositories.model_settings.ModelSettingsRepository.seed_required",
        lambda _database: (_ for _ in ()).throw(RuntimeError("seed failure")),
    )
    with pytest.raises(RuntimeError, match="seed failure"):
        _initialize(SQLiteRepository(settings))

    verification_repository = SQLiteRepository(settings)
    assert verification_repository.count_records(CredentialEncryptionMaterial) == 1
    assert verification_repository.count_records(ReferenceCountryRecord) > 0
    assert not ModelSettingsRepository(verification_repository).has_required()

###############################################################################
def test_corrupt_sqlite_file_is_not_replaced(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    original = b"not a SQLite database"
    database_path.write_bytes(original)

    with pytest.raises(Exception):
        _initialize(SQLiteRepository(_settings(database_path)))

    assert database_path.read_bytes() == original

###############################################################################
def test_sqlite_migration_lock_timeout_is_reported(monkeypatch, tmp_path: Path) -> None:

    ###############################################################################
    class _TimedOutLock:
        lock_file = str(tmp_path / "database.db.migration.lock")

        # -------------------------------------------------------------------------
        def acquire(self, *, timeout: int):
            del timeout
            raise Timeout(self.lock_file)

    monkeypatch.setattr(
        "server.repositories.database.migration_runner.FileLock",
        lambda _path: _TimedOutLock(),
    )

    with pytest.raises(DatabaseMigrationError, match="Timed out after 2s"):
        _initialize(
            SQLiteRepository(
                _settings(tmp_path / "database.db", timeout=2),
            )
        )
