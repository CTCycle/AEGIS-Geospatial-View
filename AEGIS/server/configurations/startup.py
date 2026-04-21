from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from AEGIS.server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_bootstrap_for_tests,
)
from AEGIS.server.configurations.management import ConfigurationManager
from AEGIS.server.domain.settings import ServerSettings
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.common.constants import CONFIGURATIONS_FILE


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


def run_startup_validations() -> None:
    from AEGIS.server.services.agent.tool_registry import ToolRegistry
    from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
    from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry
    from AEGIS.server.services.vector.indexer import VectorIndexer

    loader = GeospatialManifestLoader()
    loader.load_all()

    capability_registry = CapabilityRegistry(manifest_loader=loader)
    capability_registry.load_capabilities()

    runtime_registry = RuntimeRegistry(manifest_loader=loader)
    runtime_registry.build_snapshot()

    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    bindings = tool_registry.load_tool_bindings()
    tool_ids = {item["id"] for item in capability_registry.list_tools()}
    missing_bindings = [tool_id for tool_id in tool_ids if tool_id not in bindings]
    if missing_bindings:
        raise RuntimeError(
            "Missing tool bindings for: " + ", ".join(sorted(missing_bindings))
        )

    VectorIndexer(manifest_loader=loader).bootstrap_if_missing()


def reload_settings_for_tests(config_path: str | Path | None = None) -> ServerSettings:
    _cached_configuration_manager.cache_clear()
    reset_environment_bootstrap_for_tests()
    return get_server_settings(config_path)
