from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from AEGIS.server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_bootstrap_for_tests,
)
from AEGIS.server.configurations.management import ConfigurationManager
from AEGIS.server.domain.settings import ServerSettings
from AEGIS.server.utils.constants import CONFIGURATIONS_FILE


def _resolve_config_path(config_path: str | Path | None = None) -> str:
    return str(Path(config_path or CONFIGURATIONS_FILE))


@lru_cache(maxsize=4)
def _cached_configuration_manager(config_path: str) -> ConfigurationManager:
    return ConfigurationManager(config_path=config_path)


def get_configuration_manager(
    config_path: str | Path | None = None,
    *,
    force: bool = False,
) -> ConfigurationManager:
    ensure_environment_loaded(force=force)
    manager = _cached_configuration_manager(_resolve_config_path(config_path))
    if force or not manager.is_loaded:
        manager.reload()
    return manager


def get_server_settings(config_path: str | Path | None = None) -> ServerSettings:
    return get_configuration_manager(config_path=config_path).server_settings


def reload_settings_for_tests(config_path: str | Path | None = None) -> ServerSettings:
    _cached_configuration_manager.cache_clear()
    reset_environment_bootstrap_for_tests()
    return get_server_settings(config_path)
