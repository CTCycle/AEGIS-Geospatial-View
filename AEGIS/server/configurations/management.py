from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from AEGIS.server.domain.settings import AppSettings, ServerSettings
from AEGIS.server.utils.constants import CONFIGURATIONS_FILE


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _build_settings_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "database": _ensure_mapping(raw_payload.get("database")),
        "nominatim": _ensure_mapping(raw_payload.get("nominatim")),
        "geospatial": _ensure_mapping(raw_payload.get("geospatial")),
        "map": _ensure_mapping(raw_payload.get("map") or raw_payload.get("maps")),
        "jobs": _ensure_mapping(raw_payload.get("jobs")),
        "chat": _ensure_mapping(raw_payload.get("chat")),
        "vectors": _ensure_mapping(raw_payload.get("vectors")),
        "openmeteo": _ensure_mapping(raw_payload.get("openmeteo")),
        "overpass": _ensure_mapping(raw_payload.get("overpass")),
        "rainviewer": _ensure_mapping(raw_payload.get("rainviewer")),
        "gibs": _ensure_mapping(raw_payload.get("gibs")),
    }


class ConfigurationManager:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path or CONFIGURATIONS_FILE)
        self._raw_payload: dict[str, Any] = {}
        self._settings_payload: dict[str, Any] = {}
        self._app_settings: AppSettings | None = None
        self._server_settings: ServerSettings | None = None

    @property
    def config_path(self) -> Path:
        return self._config_path

    def load(self) -> AppSettings:
        self._raw_payload = self._load_raw_json()
        self._settings_payload = _build_settings_payload(self._raw_payload)
        try:
            self._app_settings = AppSettings(**self._settings_payload)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid application settings: {exc}") from exc
        self._server_settings = self._app_settings.to_server_settings()
        return self._app_settings

    def reload(self) -> AppSettings:
        return self.load()

    def get_block(self, block_name: str) -> dict[str, Any]:
        self._ensure_loaded()
        return _ensure_mapping(self._raw_payload.get(block_name))

    def get_value(self, block_name: str, key: str, default: Any = None) -> Any:
        block = self.get_block(block_name)
        return block.get(key, default)

    def get_app_settings(self) -> AppSettings:
        self._ensure_loaded()
        assert self._app_settings is not None
        return self._app_settings

    def get_server_settings(self) -> ServerSettings:
        self._ensure_loaded()
        assert self._server_settings is not None
        return self._server_settings

    def _ensure_loaded(self) -> None:
        if self._app_settings is None:
            self.load()

    def _load_raw_json(self) -> dict[str, Any]:
        if not self._config_path.exists():
            raise RuntimeError(f"Configuration file not found: {self._config_path}")
        try:
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unable to load configuration from {self._config_path}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Configuration must be a JSON object.")
        return payload
