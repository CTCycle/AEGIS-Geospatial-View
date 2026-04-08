from __future__ import annotations

import os
from typing import Any

from AEGIS.server.configurations.base import ensure_mapping, load_configuration_data
from AEGIS.server.domain.settings import (
    ChatRuntimeSettings,
    DatabaseSettings,
    GIBSSettings,
    GeospatialSettings,
    JobsSettings,
    MapSettings,
    NominatimSettings,
    ServerSettings,
    VectorRuntimeSettings,
)

from AEGIS.server.utils.constants import (
    GIBS_CAPABILITIES_ENDPOINTS,
    DEFAULT_DB_CONNECT_TIMEOUT,
    DEFAULT_DB_INSERT_BATCH_SIZE,
    DEFAULT_GIBS_DEFAULT_LAYER,
    DEFAULT_GIBS_LAYER_SYNC_USER_AGENT,
    DEFAULT_GIBS_USER_AGENT,
    DEFAULT_NOMINATIM_USER_AGENT,
    GIBS_MAX_IMAGE_DIMENSION,
    GIBS_MIN_IMAGE_DIMENSION,
    GIBS_OWS_NAMESPACES,
    GIBS_WMS_BASE_ENDPOINTS,
    NASA_ATTRIBUTION,
    NOMINATIM_SEARCH_URL,
    CONFIGURATIONS_FILE,
)

from AEGIS.server.utils.types import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_str,
    coerce_str_or_none,
)


def build_database_settings(payload: dict[str, Any] | Any) -> DatabaseSettings:
    embedded_default = coerce_bool(payload.get("embedded_database"), True)
    embedded = embedded_default

    raw_insert_batch_size = payload.get("insert_batch_size")

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
            connect_timeout=DEFAULT_DB_CONNECT_TIMEOUT,
            insert_batch_size=coerce_int(
                raw_insert_batch_size, DEFAULT_DB_INSERT_BATCH_SIZE, minimum=1
            ),
        )

    # External DB mode
    engine_value = coerce_str_or_none(payload.get("engine")) or "postgres"

    host_value = coerce_str_or_none(payload.get("host"))

    raw_port = payload.get("port")

    database_name_value = coerce_str_or_none(payload.get("database_name"))

    username_value = coerce_str_or_none(payload.get("username"))

    password_value = coerce_str_or_none(payload.get("password"))

    ssl_default = coerce_bool(payload.get("ssl"), False)
    ssl_value = ssl_default

    ssl_ca_value = coerce_str_or_none(payload.get("ssl_ca"))

    raw_connect_timeout = payload.get("connect_timeout")

    normalized_engine = engine_value.lower() if engine_value else None
    return DatabaseSettings(
        embedded_database=False,
        engine=normalized_engine,
        host=host_value,
        port=coerce_int(raw_port, 5432, minimum=1, maximum=65535),
        database_name=database_name_value,
        username=username_value,
        password=password_value,
        ssl=ssl_value,
        ssl_ca=ssl_ca_value,
        connect_timeout=coerce_int(
            raw_connect_timeout, DEFAULT_DB_CONNECT_TIMEOUT, minimum=1
        ),
        insert_batch_size=coerce_int(
            raw_insert_batch_size, DEFAULT_DB_INSERT_BATCH_SIZE, minimum=1
        ),
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
            DEFAULT_NOMINATIM_USER_AGENT,
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


def build_chat_runtime_settings(data: dict[str, Any]) -> ChatRuntimeSettings:
    payload = ensure_mapping(data)
    return ChatRuntimeSettings(
        max_history_messages=coerce_int(payload.get("max_history_messages"), 12, minimum=1, maximum=100),
    )


def build_vector_runtime_settings(data: dict[str, Any]) -> VectorRuntimeSettings:
    payload = ensure_mapping(data)
    return VectorRuntimeSettings(
        auto_sync_on_start=coerce_bool(payload.get("auto_sync_on_start"), True),
        default_ollama_embedding_model=coerce_str(
            payload.get("default_ollama_embedding_model"), "nomic-embed-text"
        ),
        default_openai_embedding_model=coerce_str(
            payload.get("default_openai_embedding_model"), "text-embedding-3-small"
        ),
        default_google_embedding_model=coerce_str(
            payload.get("default_google_embedding_model"), "text-embedding-004"
        ),
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
        user_agent=coerce_str(payload.get("user_agent"), DEFAULT_GIBS_USER_AGENT),
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
            DEFAULT_GIBS_DEFAULT_LAYER,
        ),
        capabilities_endpoints=capabilities_endpoints,
        ows_namespaces=ows_namespaces,
        layer_sync_user_agent=coerce_str(
            payload.get("layer_sync_user_agent"),
            DEFAULT_GIBS_LAYER_SYNC_USER_AGENT,
        ),
        layer_sync_timeout=coerce_float(
            payload.get("layer_sync_timeout"), 30.0, minimum=1.0
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
    chat_payload = ensure_mapping(payload.get("chat"))
    vectors_payload = ensure_mapping(payload.get("vectors"))
    gibs_payload = ensure_mapping(payload.get("gibs"))

    return ServerSettings(
        database=build_database_settings(database_payload),
        nominatim=build_nominatim_settings(nominatim_payload),
        geospatial=build_geospatial_settings(geospatial_payload),
        map=build_map_settings(map_payload),
        jobs=build_jobs_settings(jobs_payload),
        chat=build_chat_runtime_settings(chat_payload),
        vectors=build_vector_runtime_settings(vectors_payload),
        gibs=build_gibs_settings(gibs_payload),
        credential_master_key=coerce_str(
            os.getenv("AEGIS_CREDENTIAL_MASTER_KEY"),
            "dev-insecure-master-key-change-me",
        ),
        credential_key_version=coerce_str(
            os.getenv("AEGIS_CREDENTIAL_KEY_VERSION"),
            "v1",
        ),
    )


# [SERVER CONFIGURATION LOADER]
###############################################################################
def get_server_settings(config_path: str | None = None) -> ServerSettings:
    path = config_path or CONFIGURATIONS_FILE
    payload = load_configuration_data(path)

    return build_server_settings(payload)


server_settings = get_server_settings()
