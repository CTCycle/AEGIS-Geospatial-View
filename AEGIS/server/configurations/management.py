from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from AEGIS.server.domain.settings import AppSettings, ServerSettings
from AEGIS.server.utils.constants import CONFIGURATIONS_FILE


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
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
    def __init__(self, config_path: str | Path = CONFIGURATIONS_FILE) -> None:
        self.config_path = Path(config_path)
        self._payload: dict[str, Any] = {}
        self._configuration = AppSettings()
        self._server_settings = self._configuration.to_server_settings()
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def configuration(self) -> AppSettings:
        self._ensure_loaded()
        return self._configuration

    @property
    def server_settings(self) -> ServerSettings:
        self._ensure_loaded()
        return self._server_settings

    def load(self) -> "ConfigurationManager":
        payload = self._read_payload()
        configuration = self._validate_configuration(payload)
        self._payload = payload
        self._configuration = configuration
        self._server_settings = configuration.to_server_settings()
        self._loaded = True
        return self

    def reload(self) -> "ConfigurationManager":
        return self.load()

    def update(
        self, payload: dict[str, Any], *, persist: bool = True
    ) -> "ConfigurationManager":
        if not isinstance(payload, dict):
            raise RuntimeError("Configuration must be a JSON object.")

        configuration = self._validate_configuration(payload)
        self._payload = dict(payload)
        self._configuration = configuration
        self._server_settings = configuration.to_server_settings()
        self._loaded = True

        if persist:
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self

    def get_block(self, block_name: str) -> dict[str, Any]:
        self._ensure_loaded()
        return _ensure_mapping(self._payload.get(block_name))

    def get_value(self, block_name: str, key: str, default: Any = None) -> Any:
        block = self.get_block(block_name)
        return block.get(key, default)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _read_payload(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise RuntimeError(f"Configuration file not found: {self.config_path}")

        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Unable to load configuration from {self.config_path}"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Configuration must be a JSON object.")
        return payload

    def _validate_configuration(self, payload: dict[str, Any]) -> AppSettings:
        try:
            return AppSettings(**_build_settings_payload(payload))
        except ValidationError as exc:
            raise RuntimeError(f"Invalid application settings: {exc}") from exc
