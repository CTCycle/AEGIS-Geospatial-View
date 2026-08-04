from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from server.configurations import DatabaseSettings
from server.repositories.database.backend import build_database_backend
from server.repositories.database.initializer import initialize_database
from server.repositories.schemas import (
    CredentialEncryptionMaterial,
    ReferenceCountryRecord,
)
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
def test_missing_sqlite_database_creates_schema_and_seeds(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    repository = SQLiteRepository(_settings(embedded_database=True, database_path=str(database_path)))

    initialize_database(repository)

    assert database_path.is_file()
    assert repository.count_records(CredentialEncryptionMaterial) == 1
    assert repository.count_records(ReferenceCountryRecord) > 0

###############################################################################
def test_existing_sqlite_database_skips_schema_and_seeding(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    repository = SQLiteRepository(_settings(embedded_database=True, database_path=str(database_path)))
    initialize_database(repository)
    before = database_path.read_bytes()

    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda _engine: (_ for _ in ()).throw(AssertionError("schema was recreated")),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.seed_credential_encryption_material",
        lambda _database: (_ for _ in ()).throw(AssertionError("credential seed reran")),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.seed_reference_catalog",
        lambda _database: (_ for _ in ()).throw(AssertionError("catalog seed reran")),
    )

    initialize_database(
        SQLiteRepository(_settings(embedded_database=True, database_path=str(database_path)))
    )

    assert database_path.read_bytes() == before

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
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda _engine: calls.append("schema"),
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
