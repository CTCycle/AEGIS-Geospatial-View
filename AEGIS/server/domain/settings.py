from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from AEGIS.server.utils.constants import (
    CONFIGURATIONS_FILE,
    DEFAULT_DB_CONNECT_TIMEOUT,
    DEFAULT_DB_INSERT_BATCH_SIZE,
    DEFAULT_GIBS_DEFAULT_LAYER,
    DEFAULT_GIBS_LAYER_SYNC_USER_AGENT,
    DEFAULT_GIBS_USER_AGENT,
    DEFAULT_NOMINATIM_USER_AGENT,
    GIBS_CAPABILITIES_ENDPOINTS,
    GIBS_MAX_IMAGE_DIMENSION,
    GIBS_MIN_IMAGE_DIMENSION,
    GIBS_OWS_NAMESPACES,
    GIBS_WMS_BASE_ENDPOINTS,
    NASA_ATTRIBUTION,
    NOMINATIM_SEARCH_URL,
)


###############################################################################
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
class MapSettings:
    default_size_m: float
    render_delay_s: float
    tiles: str


###############################################################################
@dataclass(frozen=True)
class JobsSettings:
    polling_interval: float


###############################################################################
@dataclass(frozen=True)
class ChatRuntimeSettings:
    max_history_messages: int


###############################################################################
@dataclass(frozen=True)
class VectorRuntimeSettings:
    auto_sync_on_start: bool
    default_ollama_embedding_model: str
    default_openai_embedding_model: str
    default_google_embedding_model: str


###############################################################################
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


###############################################################################
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


###############################################################################
class JsonDatabaseSettings(BaseModel):
    embedded_database: bool = True
    engine: str = "postgres"
    host: str | None = None
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    ssl: bool = False
    ssl_ca: str | None = None
    connect_timeout: int = Field(default=DEFAULT_DB_CONNECT_TIMEOUT, ge=1)
    insert_batch_size: int = Field(default=DEFAULT_DB_INSERT_BATCH_SIZE, ge=1)

    @field_validator("host", "database_name", "username", "password", "ssl_ca", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("engine", mode="before")
    @classmethod
    def normalize_engine(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        return text or "postgres"


###############################################################################
class JsonNominatimSettings(BaseModel):
    base_url: str = NOMINATIM_SEARCH_URL
    user_agent: str = DEFAULT_NOMINATIM_USER_AGENT
    timeout: float = Field(default=10.0, ge=1.0)


###############################################################################
class JsonGeospatialSettings(BaseModel):
    min_timeline_year: int = 1900
    max_lat: float = 90.0
    min_lat: float = -90.0
    max_lon: float = 180.0
    min_lon: float = -180.0
    max_mercator_extent: float = 20037508.3427892


###############################################################################
class JsonMapSettings(BaseModel):
    default_size_m: float = Field(default=500.0, ge=1.0)
    render_delay_s: float = Field(default=1.0, ge=0.0)
    tiles: str = "OpenStreetMap"


###############################################################################
class JsonJobsSettings(BaseModel):
    polling_interval: float = 1.0


###############################################################################
class JsonChatRuntimeSettings(BaseModel):
    max_history_messages: int = Field(default=12, ge=1, le=100)


###############################################################################
class JsonVectorRuntimeSettings(BaseModel):
    auto_sync_on_start: bool = True
    default_ollama_embedding_model: str = "nomic-embed-text"
    default_openai_embedding_model: str = "text-embedding-3-small"
    default_google_embedding_model: str = "text-embedding-004"


###############################################################################
class JsonGIBSSettings(BaseModel):
    user_agent: str = DEFAULT_GIBS_USER_AGENT
    timeout: float = Field(default=20.0, ge=1.0)
    capabilities_ttl_s: float = Field(default=6 * 60 * 60, ge=60.0)
    max_cache_entries: int = Field(default=24, ge=1)
    bbox_precision: int = Field(default=6, ge=0)
    wms_base_endpoints: dict[str, str] = Field(default_factory=lambda: dict(GIBS_WMS_BASE_ENDPOINTS))
    retry_backoff_s: float = Field(default=2.0, ge=0.1)
    min_visual_radius_m: float = Field(default=20000.0, ge=1000.0)
    image_width: int = Field(
        default=1024,
        ge=GIBS_MIN_IMAGE_DIMENSION,
        le=GIBS_MAX_IMAGE_DIMENSION,
    )
    image_height: int = Field(
        default=1024,
        ge=GIBS_MIN_IMAGE_DIMENSION,
        le=GIBS_MAX_IMAGE_DIMENSION,
    )
    default_layer: str = DEFAULT_GIBS_DEFAULT_LAYER
    capabilities_endpoints: dict[str, str] = Field(default_factory=lambda: dict(GIBS_CAPABILITIES_ENDPOINTS))
    ows_namespaces: dict[str, str] = Field(default_factory=lambda: dict(GIBS_OWS_NAMESPACES))
    layer_sync_user_agent: str = DEFAULT_GIBS_LAYER_SYNC_USER_AGENT
    layer_sync_timeout: float = Field(default=30.0, ge=1.0)

    @field_validator("wms_base_endpoints", "capabilities_endpoints", "ows_namespaces", mode="before")
    @classmethod
    def normalize_string_mapping(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, str] = {}
        for key, raw in value.items():
            k = str(key).strip()
            v = str(raw).strip() if raw is not None else ""
            if k and v:
                normalized[k] = v
        return normalized


###############################################################################
def build_database_settings(payload: dict[str, Any] | Any) -> DatabaseSettings:
    if not isinstance(payload, dict):
        payload = {}
    try:
        db = JsonDatabaseSettings.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid database settings: {exc}") from exc
    return _to_database_settings(db)


###############################################################################
class JsonConfigurationSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        raw_path = getattr(settings_cls, "_configuration_file", CONFIGURATIONS_FILE)
        self.configuration_file = Path(raw_path)

    # -------------------------------------------------------------------------
    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    # -------------------------------------------------------------------------
    def __call__(self) -> dict[str, Any]:
        if not self.configuration_file.exists():
            raise RuntimeError(f"Configuration file not found: {self.configuration_file}")

        try:
            payload = json.loads(self.configuration_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unable to load configuration from {self.configuration_file}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Configuration must be a JSON object.")

        return {
            "database": payload.get("database", {}),
            "nominatim": payload.get("nominatim", {}),
            "geospatial": payload.get("geospatial", {}),
            "map": payload.get("map") or payload.get("maps", {}),
            "jobs": payload.get("jobs", {}),
            "chat": payload.get("chat", {}),
            "vectors": payload.get("vectors", {}),
            "gibs": payload.get("gibs", {}),
        }


###############################################################################
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    _configuration_file: ClassVar[str] = CONFIGURATIONS_FILE

    database: JsonDatabaseSettings = Field(default_factory=JsonDatabaseSettings)
    nominatim: JsonNominatimSettings = Field(default_factory=JsonNominatimSettings)
    geospatial: JsonGeospatialSettings = Field(default_factory=JsonGeospatialSettings)
    map: JsonMapSettings = Field(default_factory=JsonMapSettings)
    jobs: JsonJobsSettings = Field(default_factory=JsonJobsSettings)
    chat: JsonChatRuntimeSettings = Field(default_factory=JsonChatRuntimeSettings)
    vectors: JsonVectorRuntimeSettings = Field(default_factory=JsonVectorRuntimeSettings)
    gibs: JsonGIBSSettings = Field(default_factory=JsonGIBSSettings)

    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = Field(default=8000, ge=1, le=65535)
    ui_host: str = "127.0.0.1"
    ui_port: int = Field(default=8001, ge=1, le=65535)
    reload: bool = True
    optional_dependencies: bool = True
    credential_master_key: str = "dev-insecure-master-key-change-me"
    credential_key_version: str = "v1"

    @field_validator("fastapi_host", "ui_host", mode="before")
    @classmethod
    def normalize_required_strings(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        return text or "127.0.0.1"

    @field_validator("credential_master_key", "credential_key_version", mode="before")
    @classmethod
    def normalize_secret_strings(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        return text

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        _ = dotenv_settings
        return (
            init_settings,
            env_settings,
            JsonConfigurationSettingsSource(settings_cls),
            file_secret_settings,
        )

    # -------------------------------------------------------------------------
    def to_server_settings(self) -> ServerSettings:
        gibs_wms_base_endpoints = _normalize_upper_key_mapping(
            self.gibs.wms_base_endpoints,
            fallback=GIBS_WMS_BASE_ENDPOINTS,
        )
        gibs_capabilities_endpoints = _normalize_upper_key_mapping(
            self.gibs.capabilities_endpoints,
            fallback=GIBS_CAPABILITIES_ENDPOINTS,
        )
        gibs_namespaces = _normalize_key_mapping(
            self.gibs.ows_namespaces,
            fallback=GIBS_OWS_NAMESPACES,
        )

        return ServerSettings(
            database=_to_database_settings(self.database),
            nominatim=NominatimSettings(
                base_url=self.nominatim.base_url,
                user_agent=self.nominatim.user_agent,
                timeout=self.nominatim.timeout,
            ),
            geospatial=GeospatialSettings(
                min_timeline_year=self.geospatial.min_timeline_year,
                max_lat=self.geospatial.max_lat,
                min_lat=self.geospatial.min_lat,
                max_lon=self.geospatial.max_lon,
                min_lon=self.geospatial.min_lon,
                max_mercator_extent=self.geospatial.max_mercator_extent,
            ),
            map=MapSettings(
                default_size_m=self.map.default_size_m,
                render_delay_s=self.map.render_delay_s,
                tiles=self.map.tiles,
            ),
            jobs=JobsSettings(polling_interval=self.jobs.polling_interval),
            chat=ChatRuntimeSettings(max_history_messages=self.chat.max_history_messages),
            vectors=VectorRuntimeSettings(
                auto_sync_on_start=self.vectors.auto_sync_on_start,
                default_ollama_embedding_model=self.vectors.default_ollama_embedding_model,
                default_openai_embedding_model=self.vectors.default_openai_embedding_model,
                default_google_embedding_model=self.vectors.default_google_embedding_model,
            ),
            gibs=GIBSSettings(
                user_agent=self.gibs.user_agent,
                timeout=self.gibs.timeout,
                capabilities_ttl_s=self.gibs.capabilities_ttl_s,
                max_cache_entries=self.gibs.max_cache_entries,
                bbox_precision=self.gibs.bbox_precision,
                wms_base_endpoints=gibs_wms_base_endpoints,
                nasa_attribution=NASA_ATTRIBUTION,
                retry_backoff_s=self.gibs.retry_backoff_s,
                min_visual_radius_m=self.gibs.min_visual_radius_m,
                image_width=self.gibs.image_width,
                image_height=self.gibs.image_height,
                default_layer=self.gibs.default_layer,
                capabilities_endpoints=gibs_capabilities_endpoints,
                ows_namespaces=gibs_namespaces,
                layer_sync_user_agent=self.gibs.layer_sync_user_agent,
                layer_sync_timeout=self.gibs.layer_sync_timeout,
            ),
            credential_master_key=self.credential_master_key,
            credential_key_version=self.credential_key_version,
        )


# -----------------------------------------------------------------------------
def _to_database_settings(db: JsonDatabaseSettings) -> DatabaseSettings:
    if db.embedded_database:
        # Keep AEGIS behavior: external fields are ignored and timeout falls back.
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
            insert_batch_size=db.insert_batch_size,
        )

    return DatabaseSettings(
        embedded_database=False,
        engine=db.engine.strip().lower(),
        host=db.host,
        port=db.port,
        database_name=db.database_name,
        username=db.username,
        password=db.password,
        ssl=db.ssl,
        ssl_ca=db.ssl_ca,
        connect_timeout=db.connect_timeout,
        insert_batch_size=db.insert_batch_size,
    )


# -----------------------------------------------------------------------------
def _normalize_upper_key_mapping(
    mapping: dict[str, str],
    *,
    fallback: dict[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in mapping.items():
        k = str(key).strip().upper()
        v = str(value).strip()
        if k and v:
            normalized[k] = v
    return normalized or dict(fallback)


# -----------------------------------------------------------------------------
def _normalize_key_mapping(
    mapping: dict[str, str],
    *,
    fallback: dict[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in mapping.items():
        k = str(key).strip()
        v = str(value).strip()
        if k and v:
            normalized[k] = v
    return normalized or dict(fallback)

