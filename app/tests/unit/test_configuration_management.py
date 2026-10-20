from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from server.configurations.settings import AppSettings, DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.runtime_settings import RuntimeSettingsRepository
from server.repositories.schemas import Base


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


def test_runtime_repository_seeds_database_defaults_once(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)

    settings = repository.initialize_defaults()
    restarted = repository.initialize_defaults()

    assert settings.runtime_payload() == AppSettings().runtime_payload()
    assert restarted == settings
    assert _runtime_row_count(tmp_path) == 1


def test_runtime_repository_rolls_back_failed_settings_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _runtime_repository(tmp_path)

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("injected settings commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected settings commit failure"):
        repository.initialize_defaults()

    assert repository.get() is None
    assert _runtime_row_count(tmp_path) == 0


def test_existing_runtime_row_remains_authoritative(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)
    repository.initialize_defaults()
    updated = repository.update({"map": {"tiles": "CartoDB Positron"}})

    reloaded = repository.initialize_defaults()

    assert reloaded == updated
    assert reloaded.map.tiles == "CartoDB Positron"
    assert _runtime_row_count(tmp_path) == 1


def test_runtime_repository_updates_one_block_atomically(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)
    repository.initialize_defaults()

    updated = repository.update({"map": {"tiles": "CartoDB Positron"}})
    assert updated.map.tiles == "CartoDB Positron"

    with pytest.raises(ValueError, match="Unsupported runtime settings in map"):
        repository.update({"map": {"unknown_tiles": "ignored"}})

    assert repository.get_required().map.tiles == "CartoDB Positron"


def test_agent_execution_vision_policy_defaults_and_round_trip() -> None:
    defaults = AppSettings().agent_execution
    assert defaults.vision_policy == "disabled"
    assert defaults.vision_max_calls == 2

    payload = AppSettings().runtime_payload()
    payload["agent_execution"]["vision_policy"] = "on_failure"
    payload["agent_execution"]["vision_max_calls"] = 4
    reloaded = AppSettings.model_validate(payload)
    assert reloaded.agent_execution.vision_policy == "on_failure"
    assert reloaded.agent_execution.vision_max_calls == 4

    server_settings = reloaded.to_server_settings(DatabaseSettings(":memory:"))
    assert server_settings.agent_execution.vision_policy == "on_failure"
    assert server_settings.agent_execution.vision_max_calls == 4


def test_agent_execution_rejects_unknown_vision_policy() -> None:
    payload = AppSettings().runtime_payload()
    payload["agent_execution"]["vision_policy"] = "sometimes"
    with pytest.raises(Exception):
        AppSettings.model_validate(payload)
