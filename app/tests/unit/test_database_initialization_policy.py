from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from server.configurations import DatabaseSettings
from server.repositories.database.backend import build_database_backend
from server.repositories.database.initializer import initialize_database
from server.repositories.database.migration_runner import MigrationResult
from server.repositories.schemas import (
    Base,
    CredentialEncryptionMaterial,
    ReferenceCountryRecord,
)
from server.repositories.schemas.models import ConversationRecord
from server.repositories.database.sqlite import SQLiteRepository

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
def test_missing_sqlite_database_migrates_schema_and_seeds(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    repository = SQLiteRepository(_settings(embedded_database=True, database_path=str(database_path)))

    initialize_database(repository)

    assert database_path.is_file()
    assert "alembic_version" in inspect(repository.engine).get_table_names()
    assert repository.count_records(CredentialEncryptionMaterial) == 1
    assert repository.count_records(ReferenceCountryRecord) > 0

###############################################################################
def test_existing_sqlite_database_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    repository = SQLiteRepository(_settings(embedded_database=True, database_path=str(database_path)))
    initialize_database(repository)
    first_counts = (
        repository.count_records(CredentialEncryptionMaterial),
        repository.count_records(ReferenceCountryRecord),
    )

    second_repository = SQLiteRepository(
        _settings(embedded_database=True, database_path=str(database_path))
    )
    result = initialize_database(second_repository)

    assert result.migrations_applied is False
    assert (
        second_repository.count_records(CredentialEncryptionMaterial),
        second_repository.count_records(ReferenceCountryRecord),
    ) == first_counts

###############################################################################
def test_unversioned_legacy_sqlite_database_is_adopted_without_data_loss(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(embedded_database=True, database_path=str(database_path))
    legacy_repository = SQLiteRepository(settings)
    Base.metadata.create_all(legacy_repository.engine)
    with legacy_repository.session() as session:
        session.add(ConversationRecord(id="legacy-conversation", title="Preserve me"))
        session.commit()
    legacy_repository.engine.dispose()

    repository = SQLiteRepository(settings)
    result = initialize_database(repository)

    assert result.adopted_legacy_schema is True
    assert repository.count_records(ConversationRecord) == 1
    assert "alembic_version" in inspect(repository.engine).get_table_names()

###############################################################################
def test_unversioned_legacy_sqlite_schema_mismatch_fails_without_stamping(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(embedded_database=True, database_path=str(database_path))
    legacy_repository = SQLiteRepository(settings)
    Base.metadata.create_all(legacy_repository.engine)
    with legacy_repository.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE conversations ADD COLUMN unexpected TEXT")
    legacy_repository.engine.dispose()

    with pytest.raises(RuntimeError, match="does not match the pre-Alembic baseline"):
        initialize_database(SQLiteRepository(settings))

    verification_repository = SQLiteRepository(settings)
    assert "alembic_version" not in inspect(verification_repository.engine).get_table_names()

###############################################################################
def test_sqlite_migration_failure_restores_unversioned_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.db"
    settings = _settings(embedded_database=True, database_path=str(database_path))
    legacy_repository = SQLiteRepository(settings)
    Base.metadata.create_all(legacy_repository.engine)
    with legacy_repository.session() as session:
        session.add(ConversationRecord(id="rollback-conversation", title="Keep me"))
        session.commit()
    legacy_repository.engine.dispose()

    monkeypatch.setattr(
        "server.repositories.database.initializer.seed_credential_encryption_material",
        lambda _database: (_ for _ in ()).throw(RuntimeError("seed failure")),
    )
    with pytest.raises(RuntimeError, match="seed failure"):
        initialize_database(SQLiteRepository(settings))

    verification_repository = SQLiteRepository(settings)
    assert "alembic_version" not in inspect(verification_repository.engine).get_table_names()
    assert verification_repository.count_records(ConversationRecord) == 1

###############################################################################
def test_explicit_postgres_initialization_runs_provisioning_schema_and_seeding(
    monkeypatch,
) -> None:
    calls: list[str] = []
    backend = SimpleNamespace(db_path=None, engine=object())
    monkeypatch.setattr(
        "server.repositories.database.initializer._ensure_postgres_database_exists",
        lambda _database: calls.append("provision"),
    )
    def fake_migrate(_database, *, on_ready):
        calls.append("schema")
        on_ready()
        return MigrationResult(
            current_revisions=(),
            head_revisions=("head",),
            final_revisions=("head",),
            fresh_database=True,
            adopted_legacy_schema=False,
            migrations_applied=True,
        )

    monkeypatch.setattr(
        "server.repositories.database.initializer.synchronize_database",
        fake_migrate,
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.seed_credential_encryption_material",
        lambda _database: calls.append("credential"),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.seed_reference_catalog",
        lambda _database: calls.append("catalog"),
    )

    initialize_database(backend)  # type: ignore[arg-type]

    assert calls == ["provision", "schema", "credential", "catalog"]

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
