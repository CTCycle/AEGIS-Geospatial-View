from __future__ import annotations

from server.common.typing import is_json_object

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from server.common.paths import CONFIGURATIONS_FILE
from server.configurations.settings import (
    AppSettings,
    ServerSettings,
)

APPLICATION_SETTING_BLOCKS = (
    "nominatim",
    "geospatial",
    "map",
    "jobs",
    "chat",
    "openmeteo",
    "overpass",
    "rainviewer",
    "gibs",
)


###############################################################################
def _ensure_mapping(value: Any) -> dict[str, Any]:
    if is_json_object(value):
        return dict(value)
    raise RuntimeError("Configuration setting blocks must be JSON objects.")


###############################################################################
def _build_settings_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    expected = set(APPLICATION_SETTING_BLOCKS)
    unknown = sorted(set(raw_payload) - expected)
    if unknown:
        raise RuntimeError(
            "Unsupported configuration blocks: " + ", ".join(unknown)
        )
    missing = [block for block in APPLICATION_SETTING_BLOCKS if block not in raw_payload]
    if missing:
        raise RuntimeError(
            "Missing required configuration blocks: " + ", ".join(missing)
        )
    return {
        block: _ensure_mapping(raw_payload[block])
        for block in APPLICATION_SETTING_BLOCKS
    }


###############################################################################
class ConfigurationManager:
    # -------------------------------------------------------------------------
    def __init__(self, config_path: str | Path = CONFIGURATIONS_FILE) -> None:
        self.config_path = Path(config_path)
        self._payload: dict[str, Any] = {}
        self._configuration: AppSettings | None = None
        self._server_settings: ServerSettings | None = None
        self._loaded = False

    # -------------------------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # -------------------------------------------------------------------------
    @property
    def configuration(self) -> AppSettings:
        self._ensure_loaded()
        if self._configuration is None:
            raise RuntimeError("Configuration is not loaded.")
        return self._configuration

    # -------------------------------------------------------------------------
    @property
    def server_settings(self) -> ServerSettings:
        self._ensure_loaded()
        if self._server_settings is None:
            raise RuntimeError("Configuration is not loaded.")
        return self._server_settings

    # -------------------------------------------------------------------------
    def load(self) -> "ConfigurationManager":
        payload = self._read_payload()
        configuration = self._validate_configuration(payload)
        self._payload = dict(payload)
        self._configuration = configuration
        self._server_settings = configuration.to_server_settings()
        self._loaded = True
        return self

    # -------------------------------------------------------------------------
    def reload(self) -> "ConfigurationManager":
        return self.load()

    # -------------------------------------------------------------------------
    def update(
        self, payload: dict[str, Any], *, persist: bool = True
    ) -> "ConfigurationManager":
        if not is_json_object(payload):
            raise RuntimeError("Configuration must be a JSON object.")

        configuration = self._validate_configuration(payload)
        persisted_payload = dict(payload)
        self._payload = persisted_payload
        self._configuration = configuration
        self._server_settings = configuration.to_server_settings()
        self._loaded = True

        if persist:
            self.config_path.write_text(
                json.dumps(persisted_payload, indent=2), encoding="utf-8"
            )
        return self

    # -------------------------------------------------------------------------
    def get_block(self, block_name: str) -> dict[str, Any]:
        self._ensure_loaded()
        return _ensure_mapping(self._payload.get(block_name))

    # -------------------------------------------------------------------------
    def get_value(self, block_name: str, key: str, default: Any = None) -> Any:
        block = self.get_block(block_name)
        return block.get(key, default)

    # -------------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # -------------------------------------------------------------------------
    def _read_payload(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise RuntimeError(f"Configuration file not found: {self.config_path}")

        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Unable to load configuration from {self.config_path}"
            ) from exc

        if not is_json_object(payload):
            raise RuntimeError("Configuration must be a JSON object.")
        return payload

    # -------------------------------------------------------------------------
    def _validate_configuration(self, payload: dict[str, Any]) -> AppSettings:
        try:
            return AppSettings(**_build_settings_payload(payload))
        except RuntimeError:
            raise
        except ValidationError as exc:
            raise RuntimeError(f"Invalid application settings: {exc}") from exc
