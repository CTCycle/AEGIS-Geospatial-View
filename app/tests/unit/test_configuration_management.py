from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import configurations
from server.configurations.legacy_runtime_settings import (
    LegacyRuntimeSettingsError,
    load_legacy_runtime_settings,
)
from server.configurations.settings import AppSettings, DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.runtime_settings import RuntimeSettingsRepository
from server.repositories.schemas import Base


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _runtime_payload() -> dict:
    return AppSettings().runtime_payload()


def _runtime_repository(tmp_path: Path) -> RuntimeSettingsRepository:
    database = SQLiteRepository(DatabaseSettings(str(tmp_path / "runtime.db")))
    Base.metadata.create_all(database.engine)
    return RuntimeSettingsRepository(database)


def test_legacy_runtime_settings_are_validated_without_global_state(tmp_path: Path) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload["map"]["tiles"] = "CartoDB Positron"
    payload["jobs"]["polling_interval"] = 2.5
    _write_json(source, payload)

    settings = load_legacy_runtime_settings(source)

    assert settings is not None
    assert settings.map.tiles == "CartoDB Positron"
    assert settings.jobs.polling_interval == 2.5
    assert not hasattr(configurations, "server_settings")


def test_legacy_runtime_settings_reject_unknown_or_missing_blocks(tmp_path: Path) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload["database"] = {"path": "must not be accepted"}
    _write_json(source, payload)

    with pytest.raises(LegacyRuntimeSettingsError, match="Unsupported legacy"):
        load_legacy_runtime_settings(source)

    del payload["database"]
    del payload["gibs"]
    _write_json(source, payload)
    with pytest.raises(LegacyRuntimeSettingsError, match="Missing legacy"):
        load_legacy_runtime_settings(source)


def test_runtime_repository_imports_and_retires_legacy_settings(tmp_path: Path) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload["chat"]["max_history_messages"] = 24
    _write_json(source, payload)
    repository = _runtime_repository(tmp_path)

    imported = repository.initialize_defaults(legacy_path=source)

    assert imported.chat.max_history_messages == 24
    assert repository.get_required().chat.max_history_messages == 24
    assert not source.exists()


def test_runtime_repository_preserves_invalid_legacy_source(tmp_path: Path) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    del payload["gibs"]
    _write_json(source, payload)
    repository = _runtime_repository(tmp_path)

    with pytest.raises(LegacyRuntimeSettingsError, match="Missing legacy"):
        repository.initialize_defaults(legacy_path=source)

    assert source.exists()
    assert repository.get() is None


def test_runtime_repository_uses_defaults_when_legacy_source_is_absent(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)

    settings = repository.initialize_defaults(legacy_path=tmp_path / "missing.json")

    assert settings.runtime_payload() == AppSettings().runtime_payload()


def test_runtime_repository_updates_one_block_atomically(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)
    repository.initialize_defaults(legacy_path=tmp_path / "missing.json")

    updated = repository.update({"map": {"tiles": "CartoDB Positron"}})
    assert updated.map.tiles == "CartoDB Positron"

    with pytest.raises(ValueError, match="Unsupported runtime settings in map"):
        repository.update({"map": {"legacy_tiles": "ignored"}})

    assert repository.get_required().map.tiles == "CartoDB Positron"
