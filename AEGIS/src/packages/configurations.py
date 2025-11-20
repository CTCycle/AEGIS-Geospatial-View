from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

from AEGIS.src.packages.constants import (
    AGENT_MODEL_CHOICES,
    CLOUD_MODEL_CHOICES,
    CONFIGURATION_FILE,
    GIBS_MAX_IMAGE_DIMENSION,
    GIBS_MIN_IMAGE_DIMENSION,
    MAX_AGENTIC_TEMPERATURE,
    MIN_AGENTIC_TEMPERATURE,
    NASA_ATTRIBUTION,
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


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class UIRuntimeSettings:
    host: str
    port: int
    title: str
    mount_path: str
    redirect_path: str
    show_welcome_message: bool
    reconnect_timeout: int


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class APISettings:
    base_url: str


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class HTTPSettings:
    timeout: float


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class DatabaseSettings:
    selected_database: str
    database_address: str | None
    database_name: str | None
    username: str | None
    password: str | None
    insert_batch_size: int


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class NominatimSettings:
    base_url: str
    user_agent: str
    timeout: float


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class GeospatialSettings:
    min_timeline_year: int
    max_lat: float
    min_lat: float
    max_lon: float
    min_lon: float
    max_mercator_extent: float


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class MapSettings:
    default_size_m: float
    render_delay_s: float
    tiles: str


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class GIBSSettings:
    user_agent: str
    timeout: float
    capabilities_ttl_s: float
    max_cache_entries: int
    bbox_precision: int
    wms_base_endpoints: dict[str, str]
    nasa_attribution: str
    retry_backoff_s: float
    min_visual_radius_m: float
    image_width: int
    image_height: int
    default_layer: str
    capabilities_endpoints: dict[str, str]
    ows_namespaces: dict[str, str]
    layer_sync_user_agent: str
    layer_sync_timeout: float


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class ClientRuntimeDefaults:
    agent_model: str
    llm_provider: str
    cloud_model: str
    use_cloud_services: bool
    ollama_temperature: float
    ollama_reasoning: bool


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class AppConfigurations:
    backend: BackendSettings
    ui_runtime: UIRuntimeSettings
    api: APISettings
    http: HTTPSettings
    database: DatabaseSettings
    nominatim: NominatimSettings
    geospatial: GeospatialSettings
    maps: MapSettings
    gibs: GIBSSettings
    client_runtime: ClientRuntimeDefaults
    ollama_host_default: str


###############################################################################
def ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


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


###############################################################################
def build_backend_settings(data: dict[str, Any]) -> BackendSettings:
    payload = ensure_mapping(data)
    return BackendSettings(
        title=coerce_str(payload.get("title"), "AEGIS Geospatial Search Backend"),
        version=coerce_str(payload.get("version"), "0.1.0"),
        description=coerce_str(payload.get("description"), "FastAPI backend"),
    )


# -----------------------------------------------------------------------------
def build_ui_runtime_settings(data: dict[str, Any]) -> UIRuntimeSettings:
    return UIRuntimeSettings(
        host=coerce_str(data.get("host"), "0.0.0.0"),
        port=coerce_positive_int(data.get("port"), 7861),
        title=coerce_str(data.get("title"), "AEGIS Geographics"),
        mount_path=coerce_str(data.get("mount_path"), "/ui"),
        redirect_path=coerce_str(data.get("redirect_path"), "/ui"),
        show_welcome_message=coerce_bool(data.get("show_welcome_message"), False),
        reconnect_timeout=coerce_positive_int(data.get("reconnect_timeout"), 180),
    )


# -----------------------------------------------------------------------------
def build_api_settings(data: dict[str, Any]) -> APISettings:
    return APISettings(
        base_url=coerce_str(data.get("base_url"), "http://127.0.0.1:8000")
    )


# -----------------------------------------------------------------------------
def build_http_settings(data: dict[str, Any]) -> HTTPSettings:
    return HTTPSettings(timeout=coerce_float(data.get("timeout"), 3_600.0))


# -----------------------------------------------------------------------------
def build_database_settings(data: dict[str, Any]) -> DatabaseSettings:
    return DatabaseSettings(
        selected_database=coerce_str(data.get("selected_database"), "sqlite.db").lower(),
        database_address=coerce_str_or_none(data.get("database_address")),
        database_name=coerce_str_or_none(data.get("database_name")),
        username=coerce_str_or_none(data.get("username")),
        password=coerce_str_or_none(data.get("password")),
        insert_batch_size=coerce_int(data.get("insert_batch_size"), 1_000, minimum=1),
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
def build_map_settings(data: dict[str, Any]) -> MapSettings:
    payload = ensure_mapping(data)
    return MapSettings(
        default_size_m=coerce_float(payload.get("default_size_m"), 500.0, minimum=1.0),
        render_delay_s=coerce_float(payload.get("render_delay_s"), 1.0, minimum=0.0),
        tiles=coerce_str(payload.get("tiles"), "OpenStreetMap"),
    )


# -----------------------------------------------------------------------------
def build_gibs_settings(data: dict[str, Any]) -> GIBSSettings:
    payload = ensure_mapping(data)
    endpoints_payload = ensure_mapping(payload.get("wms_base_endpoints"))
    normalized_endpoints: dict[str, str] = {}
    for crs, url in endpoints_payload.items():
        crs_key = coerce_str(crs, "").upper()
        endpoint = coerce_str(url, "")
        if crs_key and endpoint:
            normalized_endpoints[crs_key] = endpoint
    if not normalized_endpoints:
        normalized_endpoints = {
            "EPSG:3857": "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
            "EPSG:4326": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
        }
    capabilities_payload = ensure_mapping(payload.get("capabilities_endpoints"))
    capabilities_endpoints: dict[str, str] = {}
    for crs, url in capabilities_payload.items():
        crs_key = coerce_str(crs, "").upper()
        endpoint = coerce_str(url, "")
        if crs_key and endpoint:
            capabilities_endpoints[crs_key] = endpoint
    if not capabilities_endpoints:
        capabilities_endpoints = {
            "EPSG:4326": "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml",
            "EPSG:3857": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml",
            "EPSG:3413": "https://gibs.earthdata.nasa.gov/wmts/epsg3413/best/1.0.0/WMTSCapabilities.xml",
            "EPSG:3031": "https://gibs.earthdata.nasa.gov/wmts/epsg3031/best/1.0.0/WMTSCapabilities.xml",
        }
    namespaces_payload = ensure_mapping(payload.get("ows_namespaces"))
    ows_namespaces: dict[str, str] = {}
    for key, value in namespaces_payload.items():
        prefix = coerce_str(key, "")
        namespace = coerce_str(value, "")
        if prefix and namespace:
            ows_namespaces[prefix] = namespace
    if not ows_namespaces:
        ows_namespaces = {"ows": "http://www.opengis.net/ows/1.1"}
    return GIBSSettings(
        user_agent=coerce_str(payload.get("user_agent"), "AEGIS-GIBS/1.0"),
        timeout=coerce_float(payload.get("timeout"), 20.0, minimum=1.0),
        capabilities_ttl_s=coerce_float(
            payload.get("capabilities_ttl_s"), 6 * 60 * 60, minimum=60.0
        ),
        max_cache_entries=coerce_int(payload.get("max_cache_entries"), 24, minimum=1),
        bbox_precision=coerce_int(payload.get("bbox_precision"), 6, minimum=0),
        wms_base_endpoints=normalized_endpoints,
        nasa_attribution=NASA_ATTRIBUTION,
        retry_backoff_s=coerce_float(payload.get("retry_backoff_s"), 2.0, minimum=0.1),
        min_visual_radius_m=coerce_float(
            payload.get("min_visual_radius_m"),
            20000.0,
            minimum=1000.0,
        ),
        image_width=coerce_int(
            payload.get("image_width"),
            1024,
            minimum=GIBS_MIN_IMAGE_DIMENSION,
            maximum=GIBS_MAX_IMAGE_DIMENSION,
        ),
        image_height=coerce_int(
            payload.get("image_height"),
            1024,
            minimum=GIBS_MIN_IMAGE_DIMENSION,
            maximum=GIBS_MAX_IMAGE_DIMENSION,
        ),
        default_layer=coerce_str(
            payload.get("default_layer"),
            "VIIRS_SNPP_CorrectedReflectance_TrueColor",
        ),
        capabilities_endpoints=capabilities_endpoints,
        ows_namespaces=ows_namespaces,
        layer_sync_user_agent=coerce_str(
            payload.get("layer_sync_user_agent"),
            "AEGIS-GIBS-LayerSync/1.0",
        ),
        layer_sync_timeout=coerce_float(
            payload.get("layer_sync_timeout"), 30.0, minimum=1.0
        ),
    )


# -----------------------------------------------------------------------------
def build_client_runtime_defaults(data: dict[str, Any]) -> ClientRuntimeDefaults:
    agent_default = AGENT_MODEL_CHOICES[0] if AGENT_MODEL_CHOICES else ""
    provider_default = coerce_str(data.get("llm_provider"), "openai").lower()
    provider_models = CLOUD_MODEL_CHOICES.get(provider_default, [])
    cloud_default = provider_models[0] if provider_models else ""
    return ClientRuntimeDefaults(
        agent_model=coerce_str(data.get("agent_model"), agent_default),
        llm_provider=provider_default,
        cloud_model=coerce_str(data.get("cloud_model"), cloud_default),
        use_cloud_services=coerce_bool(data.get("use_cloud_services"), False),
        ollama_temperature=coerce_float(data.get("ollama_temperature"), 0.7),
        ollama_reasoning=coerce_bool(data.get("ollama_reasoning"), False),
    )


# -----------------------------------------------------------------------------
def get_configurations(config_path: str | None = None) -> AppConfigurations:
    path = config_path or CONFIGURATION_FILE
    data = load_configuration_data(path)
    backend_payload = ensure_mapping(data.get("backend"))
    ui_payload = ensure_mapping(data.get("ui_runtime") or data.get("ui"))
    api_payload = ensure_mapping(data.get("api"))
    http_payload = ensure_mapping(data.get("http"))
    db_payload = ensure_mapping(data.get("database"))
    nominatim_payload = ensure_mapping(data.get("nominatim"))
    geospatial_payload = ensure_mapping(data.get("geospatial"))
    map_payload = ensure_mapping(data.get("maps"))
    gibs_payload = ensure_mapping(data.get("gibs"))
    client_payload = ensure_mapping(data.get("client_runtime_defaults"))
    ollama_host_default = coerce_str(
        data.get("ollama_host_default"), "http://localhost:11434"
    )

    backend_settings = build_backend_settings(backend_payload)
    ui_settings = build_ui_runtime_settings(ui_payload)
    api_settings = build_api_settings(api_payload)
    http_settings = build_http_settings(http_payload)
    database_settings = build_database_settings(db_payload)
    nominatim_settings = build_nominatim_settings(nominatim_payload)
    geospatial_settings = build_geospatial_settings(geospatial_payload)
    map_settings = build_map_settings(map_payload)
    gibs_settings = build_gibs_settings(gibs_payload)
    client_defaults = build_client_runtime_defaults(client_payload)

    app_config = AppConfigurations(
        backend=backend_settings,
        ui_runtime=ui_settings,
        api=api_settings,
        http=http_settings,
        database=database_settings,
        nominatim=nominatim_settings,
        geospatial=geospatial_settings,
        maps=map_settings,
        gibs=gibs_settings,
        client_runtime=client_defaults,
        ollama_host_default=ollama_host_default,
    )

    ClientRuntimeConfig.configure(app_config.client_runtime)

    return app_config


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
    def resolve_provider_and_model(cls, purpose: Literal["agent"]) -> tuple[str, str]:
        if cls.is_cloud_enabled():
            provider = cls.get_llm_provider()
            model = cls.get_cloud_model().strip()
            if not model:
                model = cls.get_agent_model()
        else:
            provider = "ollama"
            model = cls.get_agent_model()
        return provider, model.strip()


configurations = get_configurations()


__all__ = [
    "APISettings",
    "AppConfigurations",
    "BackendSettings",
    "ClientRuntimeConfig",
    "ClientRuntimeDefaults",
    "MapSettings",
    "GIBSSettings",
    "DatabaseSettings",
    "HTTPSettings",
    "UIRuntimeSettings",
    "get_configurations",
]
