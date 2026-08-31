from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import server.app as app_module
from server.configurations import environment
from server.configurations.startup import reload_settings_for_tests


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

    reload_settings_for_tests()
    try:
        application = app_module.create_app()
        with TestClient(application) as client:
            response = client.get("/api/health")

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

        assert version == ("202608310001",)
        assert credential_count == (1,)
        assert reference_count is not None and reference_count[0] > 0
    finally:
        monkeypatch.undo()
        reload_settings_for_tests()
