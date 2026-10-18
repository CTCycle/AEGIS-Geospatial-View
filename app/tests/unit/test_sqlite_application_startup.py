from __future__ import annotations

import sqlite3
import socket
from pathlib import Path

from fastapi.testclient import TestClient

import server.app as app_module
from server.configurations import environment
from server.repositories.model_settings import ModelSettingsRepository

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

        assert version == ("202609210001",)
    assert credential_count == (1,)
    assert reference_count is not None and reference_count[0] > 0


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
