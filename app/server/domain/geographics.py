from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.decision import ResolvedLocation

TimeMode = Literal["current", "historical", "forecast"]


class CapabilityKind(str, Enum):
    BASEMAP = "basemap"
    RASTER_OVERLAY = "raster-overlay"
    VECTOR_OVERLAY = "vector-overlay"
    SEARCH_INDEX = "search-index"
    CAMERA_NETWORK = "camera-network"
    DATASET_INGESTION = "dataset-ingestion"
    ANALYSIS_TOOL = "analysis-tool"
    METADATA_ONLY = "metadata-only"


class ProviderAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api-key"
    OAUTH = "oauth"
    TOKEN_HEADER = "token-header"
    PAID_OR_GATED = "paid-or-gated"


class LayerHealthStatus(str, Enum):
    FUNCTIONAL = "functional"
    PARTIAL = "partial"
    BROKEN = "broken"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class RenderingMode(str, Enum):
    XYZ = "xyz"
    WMTS = "wmts"
    WMS = "wms"
    GEOJSON = "geojson"
    VECTOR_TILE = "vector-tile"
    RASTER_TILE = "raster-tile"
    CLUSTERED_POINTS = "clustered-points"
    CHOROPLETH = "choropleth"
    CAMERA_POINTS = "camera-points"
    METADATA_ONLY = "metadata-only"


class CommercialUse(str, Enum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class EmbeddingAllowed(str, Enum):
    YES = "yes"
    NO = "no"
    METADATA_ONLY = "metadata-only"
    UNKNOWN = "unknown"


class CacheMode(str, Enum):
    NONE = "none"
    MEMORY = "memory"
    DISK = "disk"
    DATABASE = "database"
    PREPROCESSED = "preprocessed"


class LicensePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    attribution_required: bool = Field(alias="attributionRequired")
    commercial_use: CommercialUse = Field(alias="commercialUse")
    embedding_allowed: EmbeddingAllowed = Field(alias="embeddingAllowed")


class ProviderAuthPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ProviderAuthType
    required: bool = False
    provider_key: str | None = Field(default=None, alias="providerKey")
    access_page_provider_id: str | None = Field(
        default=None, alias="accessPageProviderId"
    )


class GeospatialLayersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basemaps: list[dict[str, Any]] = Field(default_factory=list)
    overlays: list[dict[str, Any]] = Field(default_factory=list)
    cameras: list[dict[str, Any]] = Field(default_factory=list)
    transit: list[dict[str, Any]] = Field(default_factory=list)


class GeospatialLayerHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str | None = None
    reliability: dict[str, Any] = Field(default_factory=dict)
    runtime: Any = None


class GeospatialProviderPayloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    provider: str
    message: str | None = None
    payload: Any = None
    attribution: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False


class GeospatialCameraDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    provider: str
    message: str | None = None
    camera: dict[str, Any] | None = None
    attribution: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False


class GeospatialCredentialStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    required: bool
    configured: bool
    environmentVariable: str | None = None


class GeospatialProviderAccountSetupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    name: str
    requires_credentials: bool
    auth_mode: str
    docs_url: str | None = None
    environment_variable: str | None = None
    configured: bool = False
    instructions: list[str] = Field(default_factory=list)


class GeospatialProviderAccountSetupListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[GeospatialProviderAccountSetupResponse] = Field(
        default_factory=list
    )


class ProviderCredentialValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    valid: bool
    status: Literal["valid", "invalid", "unsupported", "error"]
    message: str


class LayerAuditIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    manifest_id: str | None = None
    severity: str
    message: str


class CapabilityImplementationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    provider_id: str
    schema_valid: bool = True
    runtime_registered: bool
    provider_fetch_implemented: bool
    normalizer_implemented: bool
    cache_implemented: bool
    api_endpoint_covered: bool
    client_renderer_covered: bool
    unit_tested: bool
    visual_tested: bool
    placeholder_statuses: list[str] = Field(default_factory=list)


class LayerAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    schema_coverage: dict[str, int] = Field(default_factory=dict)
    provider_coverage: dict[str, int] = Field(default_factory=dict)
    renderer_coverage: dict[str, int] = Field(default_factory=dict)
    auth_coverage: dict[str, int] = Field(default_factory=dict)
    source_doc_coverage: dict[str, int] = Field(default_factory=dict)
    issues: list[LayerAuditIssue] = Field(default_factory=list)
    implementation_statuses: list[CapabilityImplementationStatus] = Field(
        default_factory=list
    )

    @property
    def ok(self) -> bool:
        return self.error_count == 0


class AgenticUsePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_enabled: bool = Field(alias="defaultEnabled")
    manual_toggle: bool = Field(alias="manualToggle")
    planner_hints: list[str] = Field(default_factory=list, alias="plannerHints")
    required_user_intent: list[str] = Field(
        default_factory=list, alias="requiredUserIntent"
    )
    avoid_when: list[str] = Field(default_factory=list, alias="avoidWhen")


class ReliabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LayerHealthStatus
    last_audited: str = Field(alias="lastAudited")
    known_limitations: list[str] = Field(default_factory=list, alias="knownLimitations")


class CachePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: CacheMode
    ttl_seconds: int = Field(ge=0, alias="ttlSeconds")
    stale_while_revalidate_seconds: int = Field(
        default=0, ge=0, alias="staleWhileRevalidateSeconds"
    )


class NormalizationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry_path: str | None = Field(default=None, alias="geometryPath")
    id_path: str | None = Field(default=None, alias="idPath")
    timestamp_path: str | None = Field(default=None, alias="timestampPath")
    field_map: dict[str, str] = Field(default_factory=dict, alias="fieldMap")
    expected_geometry: str = Field(default="not-applicable", alias="expectedGeometry")


class CapabilityManifestV2(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    provider: str
    type: str
    description: str
    capabilities: list[str]
    coverage: str
    version: int
    last_modified: str = Field(alias="last_modified")
    capability_kind: CapabilityKind = Field(alias="capabilityKind")
    rendering_mode: RenderingMode = Field(alias="renderingMode")
    source_official_docs: list[str] = Field(alias="sourceOfficialDocs")
    license: LicensePolicy
    auth: ProviderAuthPolicy
    agentic_use: AgenticUsePolicy = Field(alias="agenticUse")
    reliability: ReliabilityPolicy
    cache_policy: CachePolicy = Field(alias="cachePolicy")
    normalization: NormalizationPolicy
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    provider: str
    camera_type: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    last_update_time: datetime | None
    preview_image_url: str | None
    official_url: str
    embed_url: str | None
    embedding_allowed: bool
    stale: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class PoiFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    category: str
    source: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    address: str | None = None
    opening_hours: str | None = None
    website: str | None = None
    phone: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class ViewportPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    center_latitude: float = Field(..., ge=-90.0, le=90.0)
    center_longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_m: float = Field(default=2500.0, gt=0)
    bbox: list[float] | None = None

###############################################################################
class PresentationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emphasize_overlays: bool = False
    high_contrast: bool = False
    show_legend: bool = True

###############################################################################
class LocationSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_location: ResolvedLocation
    intent_id: str
    time_mode: TimeMode = "current"
    basemap_id: str
    overlay_ids: list[str] = Field(default_factory=list)
    viewport: ViewportPolicy
    presentation: PresentationPolicy = Field(default_factory=PresentationPolicy)

###############################################################################
class MapSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    resolved_location: ResolvedLocation
    basemap_id: str
    overlay_ids: list[str] = Field(default_factory=list)
    viewport: ViewportPolicy
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, object] = Field(default_factory=dict)
    center: dict[str, float | None] | None = None
    bounds: list[float] | None = None
    basemap: dict[str, object] | None = None
    overlays: list[dict[str, object]] = Field(default_factory=list)
    compliance_warnings: list[str] = Field(default_factory=list)


class SearchByLocationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_message: str
    map_session: MapSession

###############################################################################
class GeospatialCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[dict[str, object]] = Field(default_factory=list)
    providers: list[dict[str, object]] = Field(default_factory=list)
    basemaps: list[dict[str, object]] = Field(default_factory=list)
    overlays: list[dict[str, object]] = Field(default_factory=list)
    cameras: list[dict[str, object]] = Field(default_factory=list)
    transit: list[dict[str, object]] = Field(default_factory=list)
    tools: list[dict[str, object]] = Field(default_factory=list)
