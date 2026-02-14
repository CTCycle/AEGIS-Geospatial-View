from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from AEGIS.server.configurations.base import ensure_mapping, load_configuration_data

from AEGIS.server.utils.constants import (
    AGENT_MODEL_CHOICES,
    CLOUD_MODEL_CHOICES,
    GIBS_CAPABILITIES_ENDPOINTS,
    GIBS_MAX_IMAGE_DIMENSION,
    GIBS_MIN_IMAGE_DIMENSION,
    GIBS_OWS_NAMESPACES,
    GIBS_WMS_BASE_ENDPOINTS,
    NASA_ATTRIBUTION,
    NOMINATIM_SEARCH_URL,
    OLLAMA_DEFAULT_HOST,
    CONFIGURATIONS_FILE,
)

from AEGIS.server.utils.types import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_str,
    coerce_str_or_none,
)


###############################################################################
@dataclass
class LLMRuntimeConfig:
    defaults: LLMRuntimeDefaults | None = None
    agent_model: str = ""
    llm_provider: str = ""
    cloud_model: str = ""
    use_cloud_services: bool = False
    ollama_temperature: float = 0.0
    ollama_reasoning: bool = False
    revision: int = 0

    # -------------------------------------------------------------------------
    @classmethod
    def configure(cls, defaults: LLMRuntimeDefaults) -> None:
        cls.defaults = defaults
        cls.reset_defaults()

    # -------------------------------------------------------------------------
    @classmethod
    def _get_defaults(cls) -> LLMRuntimeDefaults:
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
        defaults = cls._get_defaults()
        value = provider.strip().lower()
        if not value:
            return cls.llm_provider
        if value not in CLOUD_MODEL_CHOICES:
            value = defaults.llm_provider
        if cls.llm_provider != value:
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
            fallback = models[0] if models else ""
            if fallback and fallback != cls.cloud_model:
                cls.cloud_model = fallback
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
        defaults = cls._get_defaults()
        try:
            parsed = float(value) if value is not None else cls.ollama_temperature
        except (TypeError, ValueError):
            parsed = defaults.ollama_temperature
        parsed = max(0.0, min(2.0, parsed))
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
            max(0.0, min(2.0, defaults.ollama_temperature)),
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
        cls,
        purpose: Literal["agent"],
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


@dataclass(frozen=True)
class DatabaseSettings:
    embedded_database: bool
    engine: str | None
    host: str | None
    port: int | None
    database_name: str | None
    username: str | None
    password: str | None
    ssl: bool
    ssl_ca: str | None
    connect_timeout: int
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
class JobsSettings:
    polling_interval: float


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
class LLMRuntimeDefaults:
    agent_model: str
    llm_provider: str
    cloud_model: str
    use_cloud_services: bool
    ollama_temperature: float
    ollama_reasoning: bool
    ollama_host_default: str


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class ServerSettings:
    database: DatabaseSettings
    nominatim: NominatimSettings
    geospatial: GeospatialSettings
    map: MapSettings
    jobs: JobsSettings
    gibs: GIBSSettings
    llm_defaults: LLMRuntimeDefaults


def build_database_settings(payload: dict[str, Any] | Any) -> DatabaseSettings:
    embedded = bool(payload.get("embedded_database", True))
    if embedded:
        # External fields are ignored entirely when embedded DB is active
        return DatabaseSettings(
            embedded_database=True,
            engine=None,
            host=None,
            port=None,
            database_name=None,
            username=None,
            password=None,
            ssl=False,
            ssl_ca=None,
            connect_timeout=10,
            insert_batch_size=coerce_int(
                payload.get("insert_batch_size"), 1000, minimum=1
            ),
        )

    # External DB mode
    engine_value = coerce_str_or_none(payload.get("engine")) or "postgres"
    normalized_engine = engine_value.lower() if engine_value else None
    return DatabaseSettings(
        embedded_database=False,
        engine=normalized_engine,
        host=coerce_str_or_none(payload.get("host")),
        port=coerce_int(payload.get("port"), 5432, minimum=1, maximum=65535),
        database_name=coerce_str_or_none(payload.get("database_name")),
        username=coerce_str_or_none(payload.get("username")),
        password=coerce_str_or_none(payload.get("password")),
        ssl=bool(payload.get("ssl", False)),
        ssl_ca=coerce_str_or_none(payload.get("ssl_ca")),
        connect_timeout=coerce_int(payload.get("connect_timeout"), 10, minimum=1),
        insert_batch_size=coerce_int(payload.get("insert_batch_size"), 1000, minimum=1),
    )


# -----------------------------------------------------------------------------
def build_nominatim_settings(data: dict[str, Any]) -> NominatimSettings:
    payload = ensure_mapping(data)
    return NominatimSettings(
        base_url=coerce_str(
            payload.get("base_url"),
            NOMINATIM_SEARCH_URL,
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
def build_jobs_settings(data: dict[str, Any]) -> JobsSettings:
    payload = ensure_mapping(data)
    return JobsSettings(
        polling_interval=coerce_float(payload.get("polling_interval"), 1.0),
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
        normalized_endpoints = dict(GIBS_WMS_BASE_ENDPOINTS)
    capabilities_payload = ensure_mapping(payload.get("capabilities_endpoints"))
    capabilities_endpoints: dict[str, str] = {}
    for crs, url in capabilities_payload.items():
        crs_key = coerce_str(crs, "").upper()
        endpoint = coerce_str(url, "")
        if crs_key and endpoint:
            capabilities_endpoints[crs_key] = endpoint
    if not capabilities_endpoints:
        capabilities_endpoints = dict(GIBS_CAPABILITIES_ENDPOINTS)
    namespaces_payload = ensure_mapping(payload.get("ows_namespaces"))
    ows_namespaces: dict[str, str] = {}
    for key, value in namespaces_payload.items():
        prefix = coerce_str(key, "")
        namespace = coerce_str(value, "")
        if prefix and namespace:
            ows_namespaces[prefix] = namespace
    if not ows_namespaces:
        ows_namespaces = dict(GIBS_OWS_NAMESPACES)
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
def build_llm_runtime_defaults(data: dict[str, Any]) -> LLMRuntimeDefaults:
    agent_default = AGENT_MODEL_CHOICES[0]
    provider_default = coerce_str(data.get("llm_provider"), "openai").lower()
    provider_models = CLOUD_MODEL_CHOICES.get(provider_default, [])
    cloud_default = provider_models[0] if provider_models else ""
    return LLMRuntimeDefaults(
        agent_model=coerce_str(data.get("agent_model"), agent_default),
        llm_provider=provider_default,
        cloud_model=coerce_str(data.get("cloud_model"), cloud_default),
        use_cloud_services=coerce_bool(data.get("use_cloud_services"), False),
        ollama_temperature=coerce_float(data.get("ollama_temperature"), 0.7),
        ollama_reasoning=coerce_bool(data.get("ollama_reasoning"), False),
        ollama_host_default=coerce_str(
            data.get("ollama_host_default"),
            OLLAMA_DEFAULT_HOST,
        ),
    )


# -----------------------------------------------------------------------------
def build_server_settings(data: dict[str, Any] | Any) -> ServerSettings:
    payload = ensure_mapping(data)
    database_payload = ensure_mapping(payload.get("database"))
    nominatim_payload = ensure_mapping(payload.get("nominatim"))
    geospatial_payload = ensure_mapping(payload.get("geospatial"))
    map_payload = ensure_mapping(payload.get("map") or payload.get("maps"))
    jobs_payload = ensure_mapping(payload.get("jobs"))
    gibs_payload = ensure_mapping(payload.get("gibs"))
    llm_defaults_payload = ensure_mapping(payload.get("llm_defaults"))
    llm_defaults = build_llm_runtime_defaults(llm_defaults_payload)
    default_provider = llm_defaults.llm_provider
    default_cloud_model = llm_defaults.cloud_model
    default_ollama_host = coerce_str(
        payload.get("ollama_base_url"),
        OLLAMA_DEFAULT_HOST,
    )

    return ServerSettings(
        database=build_database_settings(database_payload),
        nominatim=build_nominatim_settings(nominatim_payload),
        geospatial=build_geospatial_settings(geospatial_payload),
        map=build_map_settings(map_payload),
        jobs=build_jobs_settings(jobs_payload),
        gibs=build_gibs_settings(gibs_payload),
        llm_defaults=llm_defaults,
    )


# [SERVER CONFIGURATION LOADER]
###############################################################################
def get_server_settings(config_path: str | None = None) -> ServerSettings:
    path = config_path or CONFIGURATIONS_FILE
    payload = load_configuration_data(path)

    return build_server_settings(payload)


server_settings = get_server_settings()
