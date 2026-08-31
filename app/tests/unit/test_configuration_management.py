from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import configurations
from server.common.paths import CONFIGURATIONS_FILE
from server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_bootstrap_for_tests,
)
from server.configurations.management import ConfigurationManager
from server.configurations.startup import (
    get_configuration_manager,
    get_server_settings,
    reload_settings_for_tests,
)


###############################################################################
def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_configuration() -> dict:
    return json.loads(CONFIGURATIONS_FILE.read_text(encoding="utf-8"))


###############################################################################
def test_configuration_manager_loads_blocks_and_values(tmp_path: Path) -> None:
    config_file = tmp_path / "configurations.json"
    payload = _base_configuration()
    payload["map"]["tiles"] = "CartoDB Positron"
    payload["jobs"]["polling_interval"] = 2.5
    _write_json(config_file, payload)

    manager = ConfigurationManager(config_path=config_file)
    manager.load()
    app_settings = manager.configuration

    assert app_settings.map.tiles == "CartoDB Positron"
    assert manager.get_block("jobs") == {"polling_interval": 2.5}
    assert manager.get_value("jobs", "polling_interval") == 2.5
    assert manager.get_value("jobs", "missing", 99) == 99


###############################################################################
def test_configuration_manager_reload_updates_values(tmp_path: Path) -> None:
    config_file = tmp_path / "configurations.json"
    payload = _base_configuration()
    payload["jobs"]["polling_interval"] = 1.0
    _write_json(config_file, payload)
    manager = ConfigurationManager(config_path=config_file)
    manager.load()

    payload["jobs"]["polling_interval"] = 3.0
    _write_json(config_file, payload)
    manager.reload()
    app_settings = manager.configuration

    assert app_settings.jobs.polling_interval == 3.0
    assert manager.server_settings.jobs.polling_interval == 3.0


###############################################################################
def test_configuration_manager_rejects_database_block_on_update(tmp_path: Path) -> None:
    config_file = tmp_path / "configurations.json"
    _write_json(config_file, _base_configuration())
    manager = ConfigurationManager(config_path=config_file)

    payload = _base_configuration()
    payload["database"] = {"path": "should-not-persist"}
    with pytest.raises(RuntimeError, match="Unsupported configuration blocks: database"):
        manager.update(payload)


###############################################################################
def test_configuration_manager_rejects_database_block_on_load(tmp_path: Path) -> None:
    config_file = tmp_path / "configurations.json"
    payload = _base_configuration()
    payload["database"] = {"path": "ignored"}
    _write_json(config_file, payload)

    manager = ConfigurationManager(config_path=config_file)
    with pytest.raises(RuntimeError, match="Unsupported configuration blocks: database"):
        manager.load()


###############################################################################
def test_configuration_manager_rejects_missing_application_block(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "configurations.json"
    payload = _base_configuration()
    del payload["gibs"]
    _write_json(config_file, payload)

    with pytest.raises(RuntimeError, match="Missing required configuration blocks: gibs"):
        ConfigurationManager(config_path=config_file).load()


###############################################################################
def test_configuration_manager_rejects_unknown_nested_setting(tmp_path: Path) -> None:
    config_file = tmp_path / "configurations.json"
    payload = _base_configuration()
    payload["map"]["legacy_tiles"] = "ignored"
    _write_json(config_file, payload)

    with pytest.raises(RuntimeError, match="Invalid application settings"):
        ConfigurationManager(config_path=config_file).load()


###############################################################################
def test_configuration_manager_fails_on_missing_file(tmp_path: Path) -> None:
    manager = ConfigurationManager(config_path=tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="Configuration file not found"):
        manager.load()


###############################################################################
def test_startup_loads_environment_before_settings(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FASTAPI_PORT=6100\n", encoding="utf-8")
    config_file = tmp_path / "configurations.json"
    _write_json(config_file, _base_configuration())

    monkeypatch.delenv("FASTAPI_PORT", raising=False)
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    reset_environment_bootstrap_for_tests()

    app_settings = get_configuration_manager(config_path=config_file).configuration
    assert app_settings.fastapi_port == 6100


###############################################################################
def test_no_server_settings_global_export() -> None:
    assert not hasattr(configurations, "server_settings")


###############################################################################
def test_environment_loader_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    config_file = tmp_path / "configurations.json"
    env_file.write_text("UI_PORT=4555\n", encoding="utf-8")
    _write_json(config_file, _base_configuration())
    monkeypatch.delenv("UI_PORT", raising=False)
    reset_environment_bootstrap_for_tests()
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )

    ensure_environment_loaded()
    ensure_environment_loaded()

    assert (
        get_configuration_manager(
            config_path=config_file, force=True
        ).configuration.ui_port
        == 4555
    )
    reload_settings_for_tests()


###############################################################################
def test_get_server_settings_returns_runtime_settings(
    monkeypatch, tmp_path: Path
) -> None:
    config_file = tmp_path / "configurations.json"
    payload = _base_configuration()
    payload["jobs"]["polling_interval"] = 4.0
    _write_json(config_file, payload)
    reset_environment_bootstrap_for_tests()
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(tmp_path / ".env")
    )

    assert get_server_settings(config_file).jobs.polling_interval == 4.0
