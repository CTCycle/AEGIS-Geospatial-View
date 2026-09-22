from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from server import configurations
from server.configurations.legacy_runtime_settings import (
    LEGACY_REQUIRED_BLOCKS,
    LegacyRuntimeSettingsError,
    load_legacy_runtime_settings,
)
from server.configurations.settings import AppSettings, DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
import server.repositories.runtime_settings as runtime_settings_module
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


def _runtime_row_count(tmp_path: Path) -> int:
    with sqlite3.connect(tmp_path / "runtime.db") as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM application_runtime_settings"
        ).fetchone()
    assert row is not None
    return int(row[0])


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


def test_runtime_repository_commits_before_retiring_legacy_settings(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload["chat"]["max_history_messages"] = 24
    _write_json(source, payload)
    repository = _runtime_repository(tmp_path)
    original_commit = Session.commit
    original_retire = runtime_settings_module.retire_legacy_runtime_settings
    order: list[str] = []

    def tracked_commit(session: Session) -> None:
        assert source.exists()
        original_commit(session)
        order.append("commit")

    def tracked_retirement(path: Path) -> None:
        assert order == ["commit"]
        assert repository.get_required().chat.max_history_messages == 24
        order.append("retire")
        original_retire(path)

    monkeypatch.setattr(Session, "commit", tracked_commit)
    monkeypatch.setattr(
        runtime_settings_module,
        "retire_legacy_runtime_settings",
        tracked_retirement,
    )

    imported = repository.initialize_defaults(legacy_path=source)

    assert imported.chat.max_history_messages == 24
    assert repository.get_required().chat.max_history_messages == 24
    assert order == ["commit", "retire"]
    assert not source.exists()
    assert repository.initialize_defaults(legacy_path=source) == imported
    assert _runtime_row_count(tmp_path) == 1


@pytest.mark.parametrize(
    "case",
    [
        "malformed_json",
        "non_object_root",
        "missing_required_block",
        "unknown_block",
        "invalid_nested_value",
    ],
    ids=[
        "malformed-json",
        "non-object-root",
        "missing-block",
        "unknown-block",
        "invalid-nested-value",
    ],
)
def test_runtime_repository_rejects_invalid_legacy_without_fallback(
    tmp_path: Path, case: str
) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    if case == "malformed_json":
        raw = "{ malformed"
    else:
        if case == "non_object_root":
            raw = "[]"
        elif case == "missing_required_block":
            del payload["gibs"]
            raw = json.dumps(payload)
        elif case == "unknown_block":
            payload["unsupported"] = {"value": True}
            raw = json.dumps(payload)
        else:
            payload["map"]["tiles"] = {"not": "a string"}
            raw = json.dumps(payload)
    source.write_text(raw, encoding="utf-8")
    repository = _runtime_repository(tmp_path)

    with pytest.raises(LegacyRuntimeSettingsError) as error:
        repository.initialize_defaults(legacy_path=source)

    assert str(error.value)
    assert source.read_text(encoding="utf-8") == raw
    assert repository.get() is None
    assert _runtime_row_count(tmp_path) == 0


def test_runtime_repository_rolls_back_failed_settings_commit(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload["map"]["tiles"] = "CartoDB Positron"
    _write_json(source, payload)
    repository = _runtime_repository(tmp_path)

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("injected settings commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected settings commit failure"):
        repository.initialize_defaults(legacy_path=source)

    assert source.exists()
    assert repository.get() is None
    assert _runtime_row_count(tmp_path) == 0


def test_runtime_repository_keeps_committed_settings_authoritative_when_retirement_fails(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload["map"]["tiles"] = "CartoDB Positron"
    _write_json(source, payload)
    repository = _runtime_repository(tmp_path)

    def fail_retirement(_path: Path) -> None:
        raise LegacyRuntimeSettingsError("simulated locked legacy file")

    monkeypatch.setattr(
        runtime_settings_module,
        "retire_legacy_runtime_settings",
        fail_retirement,
    )
    imported = repository.initialize_defaults(legacy_path=source)
    assert imported.map.tiles == "CartoDB Positron"
    assert source.exists()

    stale_payload = _runtime_payload()
    stale_payload["map"]["tiles"] = "Stale legacy value"
    _write_json(source, stale_payload)
    restarted = repository.initialize_defaults(legacy_path=source)

    assert restarted.map.tiles == "CartoDB Positron"
    assert repository.get_required().map.tiles == "CartoDB Positron"
    assert source.exists()


def test_existing_runtime_row_wins_over_a_legacy_settings_file(
    tmp_path: Path,
) -> None:
    repository = _runtime_repository(tmp_path)
    persisted = repository.initialize_defaults(legacy_path=tmp_path / "missing.json")
    source = tmp_path / "configurations.json"
    legacy_payload = _runtime_payload()
    legacy_payload["map"]["tiles"] = "Legacy overwrite attempt"
    _write_json(source, legacy_payload)

    restarted = repository.initialize_defaults(legacy_path=source)

    assert restarted == persisted
    assert repository.get_required().map.tiles == persisted.map.tiles
    assert source.exists()
    assert _runtime_row_count(tmp_path) == 1


def test_runtime_repository_imports_every_required_legacy_block_and_defaults_new_block(
    tmp_path: Path,
) -> None:
    source = tmp_path / "configurations.json"
    payload = _runtime_payload()
    payload.pop("agent_execution")
    payload["chat"]["max_history_messages"] = 24
    payload["map"]["tiles"] = "CartoDB Positron"
    assert set(payload) == set(LEGACY_REQUIRED_BLOCKS)
    expected = AppSettings.model_validate(payload).runtime_payload()
    _write_json(source, payload)
    repository = _runtime_repository(tmp_path)

    imported = repository.initialize_defaults(legacy_path=source)

    assert imported.runtime_payload() == expected
    assert imported.agent_execution == AppSettings().agent_execution
    assert not source.exists()


def test_runtime_repository_uses_defaults_when_legacy_source_is_absent(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)

    settings = repository.initialize_defaults(legacy_path=tmp_path / "missing.json")
    restarted = repository.initialize_defaults(legacy_path=tmp_path / "missing.json")

    assert settings.runtime_payload() == AppSettings().runtime_payload()
    assert restarted == settings
    assert _runtime_row_count(tmp_path) == 1


def test_runtime_repository_updates_one_block_atomically(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)
    repository.initialize_defaults(legacy_path=tmp_path / "missing.json")

    updated = repository.update({"map": {"tiles": "CartoDB Positron"}})
    assert updated.map.tiles == "CartoDB Positron"

    with pytest.raises(ValueError, match="Unsupported runtime settings in map"):
        repository.update({"map": {"legacy_tiles": "ignored"}})

    assert repository.get_required().map.tiles == "CartoDB Positron"
