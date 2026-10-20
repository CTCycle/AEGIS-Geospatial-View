from __future__ import annotations

import json
from pathlib import Path

from server.common.paths import resolve_database_configuration_path
from server.configurations import build_database_settings
from server.configurations import database_configuration as database_config


def _isolate_configuration(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "runtime"
    monkeypatch.setenv("AEGIS_DATA_DIR", str(data_root))


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
