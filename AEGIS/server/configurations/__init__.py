from __future__ import annotations

from AEGIS.server.configurations.base import ensure_mapping, load_configuration_data
from AEGIS.server.configurations.bootstrap import ensure_environment_loaded
from AEGIS.server.configurations.server import (
    DatabaseSettings,
    GIBSSettings,
    GeospatialSettings,
    JobsSettings,
    MapSettings,
    NominatimSettings,
    ServerSettings,
    build_database_settings,
    get_app_settings,
    get_server_settings,
    reload_settings_for_tests,
    server_settings,
)
from AEGIS.server.domain.settings import AppSettings


ensure_environment_loaded()

__all__ = [
    "ensure_mapping",
    "load_configuration_data",
    "AppSettings",
    "DatabaseSettings",
    "NominatimSettings",
    "GeospatialSettings",
    "MapSettings",
    "JobsSettings",
    "GIBSSettings",
    "ServerSettings",
    "build_database_settings",
    "get_app_settings",
    "get_server_settings",
    "reload_settings_for_tests",
    "server_settings",
]

