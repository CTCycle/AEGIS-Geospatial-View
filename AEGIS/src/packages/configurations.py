from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from AEGIS.src.packages.constants import (
    AGENT_MODEL_CHOICES,
    CLOUD_MODEL_CHOICES,
    CONFIGURATION_FILE,
    DEFAULT_AGENTIC_TEMPERATURE,
    MAX_AGENTIC_TEMPERATURE,
    MIN_AGENTIC_TEMPERATURE,
)
from AEGIS.src.packages.types import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_positive_int,
    coerce_str,
    coerce_str_or_none,
)


###############################################################################
@dataclass(frozen=True)
class BackendSettings:
    title: str
    version: str
    description: str


###############################################################################
@dataclass(frozen=True)
class UIRuntimeSettings:
    host: str
    port: int
    title: str
    mount_path: str
    redirect_path: str
    show_welcome_message: bool
    reconnect_timeout: int


###############################################################################
@dataclass(frozen=True)
class APISettings:
    base_url: str


###############################################################################
@dataclass(frozen=True)
class HTTPSettings:
    timeout: float


###############################################################################
@dataclass(frozen=True)
class DatabaseSettings:
    selected_database: str
    database_address: str | None
    database_name: str | None
    username: str | None
    password: str | None
    insert_batch_size: int


###############################################################################
@dataclass(frozen=True)
class NominatimSettings:
    base_url: str
    user_agent: str
    timeout: float


###############################################################################
@dataclass(frozen=True)
class GeospatialSettings:
    min_timeline_year: int
    max_lat: float
    min_lat: float
    max_lon: float
    min_lon: float
    max_mercator_extent: float


###############################################################################
@dataclass(frozen=True)
class ClientRuntimeDefaults:
    agent_model: str
    llm_provider: str
    cloud_model: str
    use_cloud_services: bool
    ollama_temperature: float
    ollama_reasoning: bool


###############################################################################
@dataclass(frozen=True)
class AppConfigurations:
    backend: BackendSettings
    ui_runtime: UIRuntimeSettings
    api: APISettings
    http: HTTPSettings
    database: DatabaseSettings
    nominatim: NominatimSettings
    geospatial: GeospatialSettings
    client_runtime: ClientRuntimeDefaults
    ollama_host_default: str


# -----------------------------------------------------------------------------
def ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


# -----------------------------------------------------------------------------
def build_section[T](
    payload: dict[str, Any], builder: Callable[[dict[str, Any]], T]
) -> T:
    return builder(payload)


# -----------------------------------------------------------------------------
def load_configuration_data(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"Configuration file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load configuration from {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Configuration root must be a JSON object.")
    return data


# -----------------------------------------------------------------------------
def normalize_base_url(value: Any, default: str) -> str:
    candidate = coerce_str(value, default)
    normalized = candidate.rstrip("/") or default
    return normalized


# -----------------------------------------------------------------------------
def normalize_path(value: Any, default: str) -> str:
    candidate = coerce_str(value, default)
    trimmed = candidate.rstrip("/") if candidate != "/" else candidate
    if not trimmed.startswith("/"):
        trimmed = f"/{trimmed}"
    return trimmed or default


# -----------------------------------------------------------------------------
def select_agent_model(value: Any) -> str:
    fallback = AGENT_MODEL_CHOICES[0] if AGENT_MODEL_CHOICES else "llama3.1:8b"
    candidate = coerce_str(value, fallback)
    if candidate in AGENT_MODEL_CHOICES:
        return candidate
    return fallback


# -----------------------------------------------------------------------------
def select_provider_and_model(
    provider: Any, cloud_model: Any
) -> tuple[str, str]:
    fallback_provider = next(iter(CLOUD_MODEL_CHOICES), "openai")
    fallback_models = CLOUD_MODEL_CHOICES.get(fallback_provider, [])
    fallback_model = fallback_models[0] if fallback_models else ""
    normalized_provider = coerce_str(provider, fallback_provider).lower()
    if normalized_provider not in CLOUD_MODEL_CHOICES:
        normalized_provider = fallback_provider
    models = CLOUD_MODEL_CHOICES.get(normalized_provider, [])
    normalized_model = coerce_str(cloud_model, fallback_model)
    if normalized_model not in models:
        normalized_model = models[0] if models else ""
    return normalized_provider, normalized_model


# -----------------------------------------------------------------------------
def build_backend_settings(data: dict[str, Any]) -> BackendSettings:
    payload = ensure_mapping(data)
    return BackendSettings(
        title=coerce_str(
            payload.get("title"), "AEGIS Geospatial Search Backend"
        ),
        version=coerce_str(payload.get("version"), "0.1.0"),
        description=coerce_str(payload.get("description"), "FastAPI backend"),
    )


# -----------------------------------------------------------------------------
def build_ui_runtime_settings(data: dict[str, Any]) -> UIRuntimeSettings:
    payload = ensure_mapping(data)
    return UIRuntimeSettings(
        host=coerce_str(payload.get("host"), "0.0.0.0"),
        port=coerce_positive_int(payload.get("port"), 7861),
        title=coerce_str(payload.get("title"), "AEGIS Geographics"),
        mount_path=normalize_path(payload.get("mount_path"), "/ui"),
        redirect_path=normalize_path(payload.get("redirect_path"), "/ui"),
        show_welcome_message=coerce_bool(
            payload.get("show_welcome_message"), False
        ),
        reconnect_timeout=coerce_positive_int(
            payload.get("reconnect_timeout"), 180
        ),
    )


# -----------------------------------------------------------------------------
def build_api_settings(data: dict[str, Any]) -> APISettings:
    payload = ensure_mapping(data)
    base_url = normalize_base_url(
        payload.get("base_url"), "http://127.0.0.1:8000"
    )
    return APISettings(base_url=base_url)


# -----------------------------------------------------------------------------
def build_http_settings(data: dict[str, Any]) -> HTTPSettings:
    payload = ensure_mapping(data)
    timeout = coerce_float(payload.get("timeout"), 1800.0, minimum=0.1)
    return HTTPSettings(timeout=timeout)


# -----------------------------------------------------------------------------
def build_database_settings(data: dict[str, Any]) -> DatabaseSettings:
    payload = ensure_mapping(data)
    return DatabaseSettings(
        selected_database=coerce_str(payload.get("selected_database"), "sqlite"),
        database_address=coerce_str_or_none(payload.get("database_address")),
        database_name=coerce_str_or_none(payload.get("database_name")),
        username=coerce_str_or_none(payload.get("username")),
        password=coerce_str_or_none(payload.get("password")),
        insert_batch_size=coerce_positive_int(
            payload.get("insert_batch_size"), 1000
        ),
    )


# -----------------------------------------------------------------------------
def build_nominatim_settings(data: dict[str, Any]) -> NominatimSettings:
    payload = ensure_mapping(data)
    return NominatimSettings(
        base_url=coerce_str(
            payload.get("base_url"),
            "https://nominatim.openstreetmap.org/search",
        ),
        user_agent=coerce_str(
            payload.get("user_agent"),
            "AEGIS-Geographics/1.0 (contact: support@aegis.local)",
        ),
        timeout=coerce_float(payload.get("timeout"), 10.0, minimum=1.0),
    )


# -----------------------------------------------------------------------------
def build_geospatial_settings(data: dict[str, Any]) -> GeospatialSettings:
    payload = ensure_mapping(data)
    return GeospatialSettings(
        min_timeline_year=coerce_int(payload.get("min_timeline_year"), 1900),
        max_lat=coerce_float(payload.get("max_lat"), 90.0),
        min_lat=coerce_float(payload.get("min_lat"), -90.0),
        max_lon=coerce_float(payload.get("max_lon"), 180.0),
        min_lon=coerce_float(payload.get("min_lon"), -180.0),
        max_mercator_extent=coerce_float(
            payload.get("max_mercator_extent"), 20037508.3427892
        ),
    )


# -----------------------------------------------------------------------------
def build_client_runtime_defaults(
    data: dict[str, Any]
) -> ClientRuntimeDefaults:
    payload = ensure_mapping(data)
    provider, cloud_model = select_provider_and_model(
        payload.get("llm_provider"), payload.get("cloud_model")
    )
    return ClientRuntimeDefaults(
        agent_model=select_agent_model(payload.get("agent_model")),
        llm_provider=provider,
        cloud_model=cloud_model,
        use_cloud_services=coerce_bool(payload.get("use_cloud_services"), False),
        ollama_temperature=coerce_float(
            payload.get("ollama_temperature"),
            DEFAULT_AGENTIC_TEMPERATURE,
            minimum=MIN_AGENTIC_TEMPERATURE,
            maximum=MAX_AGENTIC_TEMPERATURE,
        ),
        ollama_reasoning=coerce_bool(
            payload.get("ollama_reasoning"), False
        ),
    )


###############################################################################
@dataclass
class ClientRuntimeConfig:
    defaults: ClientRuntimeDefaults | None = None
    agent_model: str = ""
    llm_provider: str = ""
    cloud_model: str = ""
    use_cloud_services: bool = False
    ollama_temperature: float = 0.0
    ollama_reasoning: bool = False
    revision: int = 0

    # -------------------------------------------------------------------------
    @classmethod
    def configure(cls, defaults: ClientRuntimeDefaults) -> None:
        cls.defaults = defaults
        cls.reset_defaults()

    # -------------------------------------------------------------------------
    @classmethod
    def _get_defaults(cls) -> ClientRuntimeDefaults:
        if cls.defaults is None:
            raise RuntimeError("Client runtime defaults are not configured.")
        return cls.defaults

    # -------------------------------------------------------------------------
    @classmethod
    def touch_revision(cls) -> None:
        cls.revision += 1

    # -------------------------------------------------------------------------
    @classmethod
    def set_agent_model(cls, model: str) -> str:
        value = model.strip()
        if value and value != cls.agent_model:
            cls.agent_model = value
            cls.touch_revision()
        return cls.agent_model

    # -------------------------------------------------------------------------
    @classmethod
    def set_llm_provider(cls, provider: str) -> str:
        value = provider.strip()
        if value and value != cls.llm_provider:
            cls.llm_provider = value
            models = CLOUD_MODEL_CHOICES.get(cls.llm_provider, [])
            if cls.cloud_model not in models:
                cls.cloud_model = models[0] if models else ""
            cls.touch_revision()
        return cls.llm_provider

    # -------------------------------------------------------------------------
    @classmethod
    def set_cloud_model(cls, model: str) -> str:
        value = model.strip()
        if not value:
            if cls.cloud_model:
                cls.cloud_model = ""
                cls.touch_revision()
            return cls.cloud_model
        models = CLOUD_MODEL_CHOICES.get(cls.llm_provider, [])
        if value not in models:
            if models and cls.cloud_model != models[0]:
                cls.cloud_model = models[0]
                cls.touch_revision()
            return cls.cloud_model
        if cls.cloud_model != value:
            cls.cloud_model = value
            cls.touch_revision()
        return cls.cloud_model

    # -------------------------------------------------------------------------
    @classmethod
    def set_use_cloud_services(cls, enabled: bool) -> bool:
        normalized = bool(enabled)
        if cls.use_cloud_services != normalized:
            cls.use_cloud_services = normalized
            cls.touch_revision()
        return cls.use_cloud_services

    # -------------------------------------------------------------------------
    @classmethod
    def set_ollama_temperature(cls, value: float | None) -> float:
        try:
            parsed = float(value) if value is not None else cls.ollama_temperature
        except (TypeError, ValueError):
            parsed = cls.ollama_temperature
        parsed = max(MIN_AGENTIC_TEMPERATURE, min(MAX_AGENTIC_TEMPERATURE, parsed))
        rounded = round(parsed, 2)
        if cls.ollama_temperature != rounded:
            cls.ollama_temperature = rounded
            cls.touch_revision()
        return cls.ollama_temperature

    # -------------------------------------------------------------------------
    @classmethod
    def set_ollama_reasoning(cls, enabled: bool) -> bool:
        normalized = bool(enabled)
        if cls.ollama_reasoning != normalized:
            cls.ollama_reasoning = normalized
            cls.touch_revision()
        return cls.ollama_reasoning

    # -------------------------------------------------------------------------
    @classmethod
    def get_agent_model(cls) -> str:
        return cls.agent_model

    # -------------------------------------------------------------------------
    @classmethod
    def get_llm_provider(cls) -> str:
        return cls.llm_provider

    # -------------------------------------------------------------------------
    @classmethod
    def get_cloud_model(cls) -> str:
        return cls.cloud_model

    # -------------------------------------------------------------------------
    @classmethod
    def is_cloud_enabled(cls) -> bool:
        return cls.use_cloud_services

    # -------------------------------------------------------------------------
    @classmethod
    def get_ollama_temperature(cls) -> float:
        return cls.ollama_temperature

    # -------------------------------------------------------------------------
    @classmethod
    def is_ollama_reasoning_enabled(cls) -> bool:
        return cls.ollama_reasoning

    # -------------------------------------------------------------------------
    @classmethod
    def reset_defaults(cls) -> None:
        defaults = cls._get_defaults()
        cls.agent_model = defaults.agent_model
        cls.llm_provider = defaults.llm_provider
        cls.cloud_model = defaults.cloud_model
        cls.use_cloud_services = defaults.use_cloud_services
        cls.ollama_temperature = round(
            max(
                MIN_AGENTIC_TEMPERATURE,
                min(MAX_AGENTIC_TEMPERATURE, defaults.ollama_temperature),
            ),
            2,
        )
        cls.ollama_reasoning = defaults.ollama_reasoning
        cls.revision = 0

    # -------------------------------------------------------------------------
    @classmethod
    def get_revision(cls) -> int:
        return cls.revision

    # -------------------------------------------------------------------------
    @classmethod
    def resolve_provider_and_model(
        cls, purpose: Literal["agent"]
    ) -> tuple[str, str]:
        if cls.is_cloud_enabled():
            provider = cls.get_llm_provider()
            model = cls.get_cloud_model().strip()
            if not model:
                model = cls.get_agent_model()
        else:
            provider = "ollama"
            model = cls.get_agent_model()
        return provider, model.strip()


# -----------------------------------------------------------------------------
def load_configurations(config_path: str | None = None) -> AppConfigurations:
    path = config_path or CONFIGURATION_FILE
    data = load_configuration_data(path)
    server_payload = ensure_mapping(data.get("server"))
    backend_payload = ensure_mapping(data.get("backend")) or ensure_mapping(
        server_payload.get("fastapi")
    )
    ui_payload = (
        ensure_mapping(data.get("ui_runtime"))
        or ensure_mapping(data.get("ui"))
        or ensure_mapping(server_payload.get("ui"))
    )
    api_payload = ensure_mapping(data.get("api"))
    http_payload = ensure_mapping(data.get("http"))
    db_payload = ensure_mapping(data.get("database"))
    nominatim_payload = ensure_mapping(data.get("nominatim"))
    geospatial_payload = ensure_mapping(data.get("geospatial"))
    client_payload = ensure_mapping(data.get("client_runtime_defaults"))
    ollama_host_default = coerce_str(
        data.get("ollama_host_default"), "http://localhost:11434"
    )

    backend_settings = build_section(backend_payload, build_backend_settings)
    ui_settings = build_section(ui_payload, build_ui_runtime_settings)
    api_settings = build_section(api_payload, build_api_settings)
    http_settings = build_section(http_payload, build_http_settings)
    database_settings = build_section(db_payload, build_database_settings)
    nominatim_settings = build_section(nominatim_payload, build_nominatim_settings)
    geospatial_settings = build_section(geospatial_payload, build_geospatial_settings)
    client_defaults = build_section(client_payload, build_client_runtime_defaults)

    app_config = AppConfigurations(
        backend=backend_settings,
        ui_runtime=ui_settings,
        api=api_settings,
        http=http_settings,
        database=database_settings,
        nominatim=nominatim_settings,
        geospatial=geospatial_settings,
        client_runtime=client_defaults,
        ollama_host_default=ollama_host_default,
    )

    ClientRuntimeConfig.configure(app_config.client_runtime)
    return app_config


APP_CONFIGURATIONS = load_configurations()


__all__ = [
    "APP_CONFIGURATIONS",
    "AppConfigurations",
    "ClientRuntimeConfig",
    "load_configurations",
]
