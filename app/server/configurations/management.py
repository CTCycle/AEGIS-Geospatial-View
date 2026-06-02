from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from server.configurations.settings import AppSettings, ServerSettings
from server.common.constants import CONFIGURATIONS_FILE


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _read_env_text(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    text = value.strip()
    return text or None


def _read_env_int(name: str) -> int | None:
    value = _read_env_text(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer value for {name}: {value}") from exc


def _read_env_bool(name: str) -> bool | None:
    value = _read_env_text(name)
    if value is None:
        return None

    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean value for {name}: {value}")


def _database_payload_from_url(database_url: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(database_url)
    scheme = (parsed.scheme or "").strip().lower()
    if not scheme:
        raise RuntimeError("DATABASE_URL must include a URL scheme.")
    if not scheme.startswith("postgresql"):
        raise RuntimeError(
            f"Unsupported DATABASE_URL scheme: {parsed.scheme}. Expected PostgreSQL."
        )

    database_name = parsed.path.lstrip("/") or None
    return {
        "engine": "postgresql+psycopg",
        "host": parsed.hostname,
        "port": parsed.port,
        "database_name": database_name,
        "username": urllib.parse.unquote(parsed.username)
        if parsed.username is not None
        else None,
        "password": urllib.parse.unquote(parsed.password)
        if parsed.password is not None
        else None,
    }


def _build_database_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {}

    database_url = _read_env_text("DATABASE_URL")
    if database_url is not None:
        payload.update(_database_payload_from_url(database_url))

    explicit_values: tuple[tuple[str, str, Any], ...] = (
        ("EMBEDDED_DATABASE", "embedded_database", _read_env_bool("EMBEDDED_DATABASE")),
        ("DATABASE_ENGINE", "engine", _read_env_text("DATABASE_ENGINE")),
        ("DATABASE_HOST", "host", _read_env_text("DATABASE_HOST")),
        ("DATABASE_PORT", "port", _read_env_int("DATABASE_PORT")),
        ("DATABASE_NAME", "database_name", _read_env_text("DATABASE_NAME")),
        ("DATABASE_USERNAME", "username", _read_env_text("DATABASE_USERNAME")),
        ("DATABASE_PASSWORD", "password", _read_env_text("DATABASE_PASSWORD")),
        ("DATABASE_SSL", "ssl", _read_env_bool("DATABASE_SSL")),
        ("DATABASE_SSL_CA", "ssl_ca", _read_env_text("DATABASE_SSL_CA")),
        (
            "DATABASE_CONNECT_TIMEOUT",
            "connect_timeout",
            _read_env_int("DATABASE_CONNECT_TIMEOUT"),
        ),
        (
            "DATABASE_INSERT_BATCH_SIZE",
            "insert_batch_size",
            _read_env_int("DATABASE_INSERT_BATCH_SIZE"),
        ),
    )

    for _env_name, key, value in explicit_values:
        if value is not None:
            payload[key] = value

    return payload


def _build_settings_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "database": _build_database_payload(),
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
        persisted_payload = dict(payload)
        persisted_payload.pop("database", None)
        self._payload = persisted_payload
        self._configuration = configuration
        self._server_settings = configuration.to_server_settings()
        self._loaded = True

        if persist:
            self.config_path.write_text(
                json.dumps(persisted_payload, indent=2), encoding="utf-8"
            )
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
