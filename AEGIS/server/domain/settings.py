from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class NominatimSettings:
    base_url: str
    user_agent: str
    timeout: float


@dataclass(frozen=True)
class GeospatialSettings:
    min_timeline_year: int
    max_lat: float
    min_lat: float
    max_lon: float
    min_lon: float
    max_mercator_extent: float


@dataclass(frozen=True)
class MapSettings:
    default_size_m: float
    render_delay_s: float
    tiles: str


@dataclass(frozen=True)
class JobsSettings:
    polling_interval: float


@dataclass(frozen=True)
class ChatRuntimeSettings:
    max_history_messages: int


@dataclass(frozen=True)
class VectorRuntimeSettings:
    auto_sync_on_start: bool
    default_ollama_embedding_model: str
    default_openai_embedding_model: str
    default_google_embedding_model: str


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


@dataclass(frozen=True)
class ServerSettings:
    database: DatabaseSettings
    nominatim: NominatimSettings
    geospatial: GeospatialSettings
    map: MapSettings
    jobs: JobsSettings
    chat: ChatRuntimeSettings
    vectors: VectorRuntimeSettings
    gibs: GIBSSettings
    credential_master_key: str
    credential_key_version: str
