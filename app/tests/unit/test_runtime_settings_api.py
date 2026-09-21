from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.settings import router
from server.configurations.settings import DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.runtime_settings import RuntimeSettingsRepository
from server.repositories.schemas import Base
from server.services.settings.runtime_settings import RuntimeSettingsService


def _client(tmp_path: Path) -> tuple[TestClient, RuntimeSettingsRepository]:
    database = SQLiteRepository(DatabaseSettings(str(tmp_path / "runtime.db")))
    Base.metadata.create_all(database.engine)
    repository = RuntimeSettingsRepository(database)
    repository.initialize_defaults(legacy_path=tmp_path / "missing.json")
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.state.runtime_settings_service = RuntimeSettingsService(repository)
    return TestClient(application), repository


def test_runtime_settings_api_returns_typed_blocks_and_restart_metadata(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.get("/api/settings/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["chat"]["max_history_messages"] == 12
    assert payload["agent_execution"]["max_iterations"] == 12
    assert payload["restart_required"] is False
    assert "credentials" not in payload
    assert repository.get_required().chat.max_history_messages == 12


def test_runtime_settings_api_merges_partial_blocks_atomically(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.patch(
        "/api/settings/runtime",
        json={"chat": {"max_history_messages": 24}},
    )

    assert response.status_code == 200
    assert response.json()["chat"]["max_history_messages"] == 24
    assert response.json()["restart_required"] is True
    assert repository.get_required().chat.max_history_messages == 24


def test_runtime_settings_api_rejects_unknown_nested_fields(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.patch(
        "/api/settings/runtime",
        json={"map": {"legacy_tiles": "ignored"}},
    )

    assert response.status_code == 400
    assert "Unsupported runtime settings in map" in response.json()["detail"]
    assert repository.get_required().map.tiles == "OpenStreetMap"
