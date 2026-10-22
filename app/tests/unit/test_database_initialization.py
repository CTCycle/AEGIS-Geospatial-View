from __future__ import annotations
import json
import pytest
import sqlite3
import socket
import server.app as app_module
from pathlib import Path
from server.common.paths import resolve_database_configuration_path
from server.configurations import build_database_settings, database_configuration as database_config, DatabaseSettings, environment
from filelock import Timeout
from sqlalchemy import inspect, text
from server.repositories.database import migration_runner
from server.repositories.database.initializer import initialize_database
from server.repositories.database.migration_runner import DatabaseMigrationError
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base, CredentialEncryptionMaterial, ReferenceCountryRecord
from server.repositories.schemas.models import ApplicationRuntimeSettingsRecord, ConversationRecord, ModelProviderSettingsRecord
from server.repositories.model_settings import ModelSettingsRepository
from server.services.catalog.startup import seed_reference_catalog
from fastapi.testclient import TestClient
from server.repositories.database.engine import configure_sqlite_connection

# --- test_database_configuration.py ---




###############################################################################
def _isolate_configuration(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "runtime"
    monkeypatch.setenv("AEGIS_DATA_DIR", str(data_root))


###############################################################################
def test_first_run_writes_database_only_configuration_and_uses_its_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _isolate_configuration(monkeypatch, tmp_path)

    settings = build_database_settings()
    config_path = resolve_database_configuration_path()
    stored = json.loads(config_path.read_text(encoding="utf-8"))

    assert settings.database_path == str(tmp_path / "runtime" / "database.db")
    assert settings.sqlite_lock_timeout_seconds == 60
    assert stored == {
        "schema_version": 1,
        "backend": "sqlite",
        "database_path": str(tmp_path / "runtime" / "database.db"),
        "sqlite_lock_timeout_seconds": 60,
    }
    assert not set(stored) & {"FASTAPI_PORT", "UI_PORT", "application_settings"}


###############################################################################
def test_existing_database_configuration_is_the_only_runtime_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _isolate_configuration(monkeypatch, tmp_path)
    database_config.save_database_configuration(
        database_config.DatabaseConfiguration(
            database_path=str(tmp_path / "chosen.sqlite"),
            sqlite_lock_timeout_seconds=15,
        )
    )

    settings = build_database_settings()

    assert settings.database_path == str(tmp_path / "chosen.sqlite")
    assert settings.sqlite_lock_timeout_seconds == 15


###############################################################################
def test_invalid_primary_recovers_from_valid_backup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _isolate_configuration(monkeypatch, tmp_path)
    config_path = resolve_database_configuration_path()
    config_path.parent.mkdir(parents=True)
    backup_path = config_path.with_name(f"{config_path.name}.bak")
    recovered = database_config.DatabaseConfiguration(
        database_path=str(tmp_path / "recovered.sqlite"),
        sqlite_lock_timeout_seconds=23,
    )
    backup_path.write_text(recovered.model_dump_json(), encoding="utf-8")
    config_path.write_text('{"schema_version": "bad"}', encoding="utf-8")

    loaded = database_config.load_database_configuration()

    assert loaded == recovered
    assert database_config._read_configuration(config_path) == recovered


###############################################################################
def test_atomic_save_keeps_last_valid_configuration_as_backup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _isolate_configuration(monkeypatch, tmp_path)
    first = database_config.DatabaseConfiguration(
        database_path=str(tmp_path / "one.sqlite")
    )
    second = database_config.DatabaseConfiguration(
        database_path=str(tmp_path / "two.sqlite")
    )

    database_config.save_database_configuration(first)
    database_config.save_database_configuration(second)

    config_path = resolve_database_configuration_path()
    backup_path = config_path.with_name(f"{config_path.name}.bak")
    assert database_config._read_configuration(config_path) == second
    assert database_config._read_configuration(backup_path) == first
    assert not list(config_path.parent.glob("*.tmp"))

# --- test_database_initialization_policy.py ---




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

# --- test_sqlite_application_startup.py ---




###############################################################################
def test_application_starts_against_isolated_sqlite_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "runtime"
    env_file = tmp_path / "settings" / ".env"
    example_file = tmp_path / "settings" / ".env.example"
    env_file.parent.mkdir()
    env_file.write_text(f"AEGIS_DATA_DIR={data_dir}\n", encoding="utf-8")
    example_file.write_text(env_file.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(environment, "ENV_FILE_PATH", env_file)
    monkeypatch.setattr(environment, "ENV_EXAMPLE_FILE_PATH", example_file)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)
    monkeypatch.delenv("AEGIS_DATA_DIR", raising=False)

    environment.reset_environment_bootstrap_for_tests()
    try:
        application = app_module.create_app()
        with TestClient(application) as client:
            response = client.get("/api/health")
    finally:
        environment.reset_environment_bootstrap_for_tests()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    database_path = data_dir / "database.db"
    assert database_path.is_file()
    assert (data_dir / "database-settings.json").is_file()
    with sqlite3.connect(database_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        credential_count = connection.execute(
            "SELECT COUNT(*) FROM credential_encryption_materials"
        ).fetchone()
        reference_count = connection.execute(
            "SELECT COUNT(*) FROM reference_countries"
        ).fetchone()

        assert version == ("202608200001",)
    assert credential_count == (1,)
    assert reference_count is not None and reference_count[0] > 0


###############################################################################
def test_dynamic_provider_outage_does_not_block_isolated_application_startup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "runtime"
    env_file = tmp_path / "settings" / ".env"
    example_file = tmp_path / "settings" / ".env.example"
    env_file.parent.mkdir()
    env_file.write_text(f"AEGIS_DATA_DIR={data_dir}\n", encoding="utf-8")
    example_file.write_text(env_file.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(environment, "ENV_FILE_PATH", env_file)
    monkeypatch.setattr(environment, "ENV_EXAMPLE_FILE_PATH", example_file)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)
    monkeypatch.delenv("AEGIS_DATA_DIR", raising=False)

    original_initialize = app_module.initialize_database
    network_attempts: list[object] = []
    selected_settings = []

    def initialize_with_unavailable_provider(database, **kwargs):
        result = original_initialize(database, **kwargs)
        database_path = Path(str(database.engine.url.database)).resolve()
        assert database_path.is_relative_to(data_dir.resolve())
        selected_settings.append(
            ModelSettingsRepository(database).update(
                active_provider_mode="cloud",
                agent_model_provider="deepseek",
                agent_model_name="deepseek-chat",
                ollama_url="http://127.0.0.1:11434",
                openai_base_url=None,
                google_base_url=None,
                deepseek_base_url="http://127.0.0.1:1/v1",
            )
        )
        return result

    def simulated_provider_outage(address, *args, **kwargs):
        network_attempts.append(address)
        raise OSError("simulated dynamic-provider outage")

    monkeypatch.setattr(
        app_module, "initialize_database", initialize_with_unavailable_provider
    )
    monkeypatch.setattr(socket, "create_connection", simulated_provider_outage)

    environment.reset_environment_bootstrap_for_tests()
    try:
        with TestClient(app_module.create_app()) as client:
            response = client.get("/api/health")
    finally:
        environment.reset_environment_bootstrap_for_tests()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(selected_settings) == 1
    assert selected_settings[0].agent_model_provider == "deepseek"
    assert network_attempts == []
    assert (data_dir / "database.db").is_file()


###############################################################################
def test_database_switch_keeps_each_database_settings_independent_and_survives_restart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "runtime"
    env_file = tmp_path / "settings" / ".env"
    example_file = tmp_path / "settings" / ".env.example"
    env_file.parent.mkdir()
    env_file.write_text(f"AEGIS_DATA_DIR={data_dir}\n", encoding="utf-8")
    example_file.write_text(env_file.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(environment, "ENV_FILE_PATH", env_file)
    monkeypatch.setattr(environment, "ENV_EXAMPLE_FILE_PATH", example_file)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)
    monkeypatch.delenv("AEGIS_DATA_DIR", raising=False)

    environment.reset_environment_bootstrap_for_tests()
    try:
        with TestClient(app_module.create_app()) as client:
            original_path = str(data_dir / "database.db")
            assert (
                client.get("/api/settings/database").json()["database_path"]
                == original_path
            )
            assert (
                client.patch(
                    "/api/settings/runtime",
                    json={"chat": {"max_history_messages": 18}},
                ).status_code
                == 200
            )

            target = {
                "backend": "sqlite",
                "database_path": str(data_dir / "alternate.sqlite"),
                "sqlite_lock_timeout_seconds": 60,
            }
            tested = client.post("/api/settings/database/test", json=target)
            assert tested.status_code == 200
            assert tested.json()["schema_status"] == "empty"

            switched = client.put("/api/settings/database", json=target)
            assert switched.status_code == 200
            assert (
                client.get("/api/settings/runtime").json()["chat"][
                    "max_history_messages"
                ]
                == 12
            )
            assert (
                client.patch(
                    "/api/settings/runtime",
                    json={"chat": {"max_history_messages": 8}},
                ).status_code
                == 200
            )

            switched_back = client.put(
                "/api/settings/database",
                json={
                    **target,
                    "database_path": original_path,
                },
            )
            assert switched_back.status_code == 200
            assert (
                client.get("/api/settings/runtime").json()["chat"][
                    "max_history_messages"
                ]
                == 18
            )
    finally:
        environment.reset_environment_bootstrap_for_tests()

    with TestClient(app_module.create_app()) as restarted_client:
        assert restarted_client.get("/api/settings/database").json()[
            "database_path"
        ] == str(data_dir / "database.db")
        assert (
            restarted_client.get("/api/settings/runtime").json()["chat"][
                "max_history_messages"
            ]
            == 18
        )
    assert (data_dir / "database-settings.json").is_file()

# --- test_sqlite_engine_listener.py ---




###############################################################################
class _Cursor:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.statements: list[str] = []

    # -------------------------------------------------------------------------
    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    # -------------------------------------------------------------------------
    def close(self) -> None:
        return None

###############################################################################
class _Connection:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    # -------------------------------------------------------------------------
    def cursor(self) -> _Cursor:
        return self.cursor_instance

###############################################################################
def test_sqlite_connection_listener_applies_expected_pragmas() -> None:
    connection = _Connection()

    configure_sqlite_connection(connection)

    assert connection.cursor_instance.statements == [
        "PRAGMA foreign_keys=ON",
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=5000",
        "PRAGMA synchronous=NORMAL",
    ]

###############################################################################
def test_sqlite_engine_applies_pragmas_to_live_connections(tmp_path: Path) -> None:
    repository = SQLiteRepository(
        DatabaseSettings(database_path=str(tmp_path / "database.db"))
    )

    with repository.engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
        assert connection.scalar(text("PRAGMA synchronous")) == 1

    repository.engine.dispose()

# --- test_sqlite_repository.py ---



###############################################################################
def test_repository_creates_parent_directory_for_database_path(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "data" / "database.db"

    repository = SQLiteRepository(DatabaseSettings(database_path=str(database_path)))

    assert database_path.parent.is_dir()
    repository.engine.dispose()

###############################################################################
def test_repository_counts_records_using_short_lived_sessions(tmp_path: Path) -> None:
    repository = SQLiteRepository(
        DatabaseSettings(database_path=str(tmp_path / "database.db"))
    )
    Base.metadata.create_all(repository.engine)

    with repository.session() as session:
        session.add(ReferenceCountryRecord(iso2="IT", name="Italy", name_key="italy"))
        session.commit()

    assert repository.count_records(ReferenceCountryRecord) == 1
    repository.engine.dispose()