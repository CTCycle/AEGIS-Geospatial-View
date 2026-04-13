from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from AEGIS.server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_loader_for_tests,
)
from AEGIS.server.configurations.management import ConfigurationManager
from AEGIS.server.domain.settings import AppSettings, ServerSettings
from AEGIS.server.utils.constants import CONFIGURATIONS_FILE


def _normalize_config_path(config_path: str | Path | None) -> str:
    return str(Path(config_path or CONFIGURATIONS_FILE).resolve())


@lru_cache(maxsize=4)
def _cached_manager(config_path: str) -> ConfigurationManager:
    return ConfigurationManager(config_path=config_path)


def initialize_configurations(*, force: bool = False, config_path: str | Path | None = None) -> ConfigurationManager:
    ensure_environment_loaded(force=force)
    manager = _cached_manager(_normalize_config_path(config_path))
    if force:
        manager.reload()
    else:
        manager.load()
    return manager


def get_configuration_manager(config_path: str | Path | None = None) -> ConfigurationManager:
    return initialize_configurations(config_path=config_path)


def get_app_settings(config_path: str | Path | None = None) -> AppSettings:
    return get_configuration_manager(config_path=config_path).get_app_settings()


def get_server_settings(config_path: str | Path | None = None) -> ServerSettings:
    return get_configuration_manager(config_path=config_path).get_server_settings()


def reload_settings_for_tests() -> AppSettings:
    _cached_manager.cache_clear()
    reset_environment_loader_for_tests()
    return get_app_settings()
