from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from AEGIS.src.packages.configurations import ensure_mapping, load_configuration_data
from AEGIS.src.packages.constants import (
    AGENT_MODEL_CHOICES,
    CLOUD_MODEL_CHOICES,   
    GIBS_MAX_IMAGE_DIMENSION,
    GIBS_MIN_IMAGE_DIMENSION,   
    NASA_ATTRIBUTION,
    SERVER_CONFIGURATION_FILE,
)

from AEGIS.src.packages.types import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_positive_int,
    coerce_str,
    coerce_str_or_none,
)



# [SERVER SETTINGS]
###############################################################################
@dataclass(frozen=True)
class FastAPISettings:
    title: str
    description: str
    version: str   

# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class ServerSettings:
    fastapi: FastAPISettings
    database: DatabaseSettings     
    nominatim: NominatimSettings
    geospatial: GeospatialSettings
    map: MapSettings
    gibs: GIBSSettings
    llm_defaults: LLMRuntimeDefaults


# [BUILDER FUNCTIONS]
###############################################################################
def build_fastapi_settings(data: dict[str, Any]) -> FastAPISettings:
    payload = ensure_mapping(data)
    return FastAPISettings(
        title=coerce_str(payload.get("title"), "AEGIS Geospatial Search Backend"),
        version=coerce_str(payload.get("version"), "0.1.0"),
        description=coerce_str(payload.get("description"), "FastAPI backend"),        
    )

# -----------------------------------------------------------------------------
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
            insert_batch_size=coerce_int(payload.get("insert_batch_size"), 1000, minimum=1),
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
def build_llm_runtime_defaults(data: dict[str, Any]) -> LLMRuntimeDefaults:
    agent_default = AGENT_MODEL_CHOICES[0] if AGENT_MODEL_CHOICES else ""
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
    )
   
# -----------------------------------------------------------------------------
def build_server_settings(data: dict[str, Any] | Any) -> ServerSettings:
    payload = ensure_mapping(data)
    fastapi_payload = ensure_mapping(payload.get("fastapi"))
    database_payload = ensure_mapping(payload.get("database"))
    nominatim_payload = ensure_mapping(payload.get("nominatim"))
    geospatial_payload = ensure_mapping(payload.get("geospatial"))
    map_payload = ensure_mapping(payload.get("map"))
    gibs_payload = ensure_mapping(payload.get("gibs"))
    llm_defaults_payload = ensure_mapping(
    payload.get("llm_runtime_defaults") or payload.get("llm_defaults")
    )
    llm_defaults = build_llm_runtime_defaults(llm_defaults_payload)

    return ServerSettings(
        fastapi=build_fastapi_settings(fastapi_payload),
        database=build_database_settings(database_payload),
        nominatim=build_nominatim_settings(nominatim_payload),
        geospatial=build_geospatial_settings(geospatial_payload),
        map=build_map_settings(map_payload),
        gibs=build_gibs_settings(gibs_payload),
        llm_defaults=llm_defaults,
    )


# [SERVER CONFIGURATION LOADER]
###############################################################################
def get_server_settings(config_path: str | None = None) -> ServerSettings:
    path = config_path or SERVER_CONFIGURATION_FILE
    payload = load_configuration_data(path)

    return build_server_settings(payload)


server_settings = get_server_settings()
