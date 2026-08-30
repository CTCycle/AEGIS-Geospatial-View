from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now
from server.contracts.extraction import ViewportIntent
from server.domain.agent.decision import ResolvedLocation

TimeMode = Literal["current", "historical", "forecast"]
InspectionAssociation = Literal[
    "feature",
    "location",
    "overlay",
    "non_spatial",
]


GeospatialProviderAutomationSupport = Literal[
    "manual_only", "guided_playwright", "agent_assisted", "unsupported"
]
GeospatialProviderSignupFieldType = Literal["text", "email", "textarea", "select"]


###############################################################################
class CapabilityKind(str, Enum):
    BASEMAP = "basemap"
    RASTER_OVERLAY = "raster-overlay"
    VECTOR_OVERLAY = "vector-overlay"
    SEARCH_INDEX = "search-index"
    CAMERA_NETWORK = "camera-network"
    DATASET_INGESTION = "dataset-ingestion"
    ANALYSIS_TOOL = "analysis-tool"
    METADATA_ONLY = "metadata-only"


###############################################################################
class ProviderAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api-key"
    OAUTH = "oauth"
    TOKEN_HEADER = "token-header"
    PAID_OR_GATED = "paid-or-gated"


###############################################################################
class LayerHealthStatus(str, Enum):
    FUNCTIONAL = "functional"
    PARTIAL = "partial"
    BROKEN = "broken"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


###############################################################################
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


###############################################################################
class CommercialUse(str, Enum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


###############################################################################
class EmbeddingAllowed(str, Enum):
    YES = "yes"
    NO = "no"
    METADATA_ONLY = "metadata-only"
    UNKNOWN = "unknown"


###############################################################################
class CacheMode(str, Enum):
    NONE = "none"
    MEMORY = "memory"
    DISK = "disk"
    DATABASE = "database"
    PREPROCESSED = "preprocessed"


###############################################################################
class LicensePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    attribution_required: bool = Field(alias="attributionRequired")
    commercial_use: CommercialUse = Field(alias="commercialUse")
    embedding_allowed: EmbeddingAllowed = Field(alias="embeddingAllowed")


###############################################################################
class ProviderAuthPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ProviderAuthType
    required: bool = False
    provider_key: str | None = Field(default=None, alias="providerKey")
    access_page_provider_id: str | None = Field(
        default=None, alias="accessPageProviderId"
    )


###############################################################################
class GeospatialLayersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basemaps: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    overlays: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    cameras: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    transit: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )


###############################################################################
class GeospatialLayerHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str | None = None
    reliability: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    runtime: Any = None


###############################################################################
class GeospatialProviderPayloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    provider: str
    message: str | None = None
    payload: Any = None
    attribution: list[str] = Field(default_factory=lambda: list[str]())
    warnings: list[str] = Field(default_factory=lambda: list[str]())
    stale: bool = False
    result_status: str | None = None
    result_type: str | None = None
    error_code: str | None = None


###############################################################################
class GeospatialLayerRenderDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    layer_id: str
    rendering_mode: str
    source_protocol: str
    url: str | None = None
    tile_url_template: str | None = None
    crs: str | None = None
    format: str | None = None
    style: str | None = None
    time: str | None = None
    default_time: str | None = None
    tile_matrix_set: str | None = None
    tile_size: int | None = None
    min_zoom: int | None = None
    max_zoom: int | None = None
    attribution: list[str] = Field(default_factory=lambda: list[str]())
    warnings: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class GeospatialProviderLayerDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    layer_id: str
    title: str
    abstract: str | None = None
    rendering_mode: str
    source_protocol: str
    data_format: str
    geometry_type: str
    queryable: bool = False
    crs: list[str] = Field(default_factory=lambda: list[str]())
    formats: list[str] = Field(default_factory=lambda: list[str]())
    styles: list[str] = Field(default_factory=lambda: list[str]())
    time_extent: str | None = None
    default_time: str | None = None
    tile_matrix_sets: list[str] = Field(default_factory=lambda: list[str]())
    render: GeospatialLayerRenderDescriptor | None = None
    attribution: list[str] = Field(default_factory=lambda: list[str]())
    warnings: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class GeospatialProviderLayersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    layers: list[GeospatialProviderLayerDescriptor]
    warnings: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class GeospatialProviderLayerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    layer: GeospatialProviderLayerDescriptor
    warnings: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class GeospatialCameraDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    provider: str
    message: str | None = None
    camera: dict[str, Any] | None = None
    attribution: list[str] = Field(default_factory=lambda: list[str]())
    warnings: list[str] = Field(default_factory=lambda: list[str]())
    stale: bool = False


###############################################################################
class GeospatialCredentialStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    required: bool
    configured: bool
    environmentVariable: str | None = None


###############################################################################
class GeospatialProviderSignupField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    field_type: GeospatialProviderSignupFieldType = "text"
    required: bool = True
    sensitive: bool = False
    help_text: str | None = None


###############################################################################
class GeospatialProviderSignupAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    support: GeospatialProviderAutomationSupport
    signup_url: str | None = None
    developer_portal_url: str | None = None
    docs_url: str | None = None
    required_fields: list[GeospatialProviderSignupField] = Field(
        default_factory=lambda: list[GeospatialProviderSignupField]()
    )
    user_action_notes: list[str] = Field(default_factory=lambda: list[str]())
    safety_notes: list[str] = Field(default_factory=lambda: list[str]())
    experimental: bool = True
    experimental_label: str = "Experimental guided setup"


###############################################################################
class GeospatialProviderAccountSetupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    name: str
    requires_credentials: bool
    auth_mode: str
    docs_url: str | None = None
    environment_variable: str | None = None
    configured: bool = False
    instructions: list[str] = Field(default_factory=lambda: list[str]())
    automation: GeospatialProviderSignupAutomation
    credential_storage_key: str
    credential_label: str
    key_format_hint: str | None = None
    validation_supported: bool = False


###############################################################################
class GeospatialProviderAccountSetupListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[GeospatialProviderAccountSetupResponse] = Field(
        default_factory=lambda: list[GeospatialProviderAccountSetupResponse]()
    )


###############################################################################
class ProviderCredentialValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    valid: bool
    status: Literal["valid", "invalid", "unsupported", "error"]
    message: str


###############################################################################
class LayerAuditIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    manifest_id: str | None = None
    severity: str
    message: str


###############################################################################
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
    placeholder_statuses: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class LayerAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    schema_coverage: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    provider_coverage: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    renderer_coverage: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    auth_coverage: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    source_doc_coverage: dict[str, int] = Field(
        default_factory=lambda: dict[str, int]()
    )
    issues: list[LayerAuditIssue] = Field(
        default_factory=lambda: list[LayerAuditIssue]()
    )
    implementation_statuses: list[CapabilityImplementationStatus] = Field(
        default_factory=lambda: list[CapabilityImplementationStatus]()
    )

    # -------------------------------------------------------------------------
    @property
    def ok(self) -> bool:
        return self.error_count == 0


###############################################################################
class AgenticUsePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_enabled: bool = Field(alias="defaultEnabled")
    manual_toggle: bool = Field(alias="manualToggle")
    planner_hints: list[str] = Field(default_factory=list, alias="plannerHints")
    required_user_action: list[str] = Field(
        default_factory=list, alias="requiredUserAction"
    )
    avoid_when: list[str] = Field(default_factory=list, alias="avoidWhen")


###############################################################################
class ReliabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LayerHealthStatus
    last_audited: str = Field(alias="lastAudited")
    known_limitations: list[str] = Field(default_factory=list, alias="knownLimitations")


###############################################################################
class CachePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: CacheMode
    ttl_seconds: int = Field(ge=0, alias="ttlSeconds")
    stale_while_revalidate_seconds: int = Field(
        default=0, ge=0, alias="staleWhileRevalidateSeconds"
    )


###############################################################################
class NormalizationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry_path: str | None = Field(default=None, alias="geometryPath")
    id_path: str | None = Field(default=None, alias="idPath")
    timestamp_path: str | None = Field(default=None, alias="timestampPath")
    field_map: dict[str, str] = Field(default_factory=dict, alias="fieldMap")
    expected_geometry: str = Field(default="not-applicable", alias="expectedGeometry")


###############################################################################
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
    metadata: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


###############################################################################
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
    metadata: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


###############################################################################
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
    metadata: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


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
class ProviderLayerSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    layer_id: str
    time: str | None = None
    style: str | None = None
    format: str | None = None
    render: dict[str, object] | None = None


###############################################################################
class InspectionField(BaseModel):
    """A bounded, allowlisted scalar exposed by the map inspection UI."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    value: str | int | float | bool | None
    unit: str | None = None
    category: str = "general"
    source_url: str | None = None
    order: int = 0


###############################################################################
class MapInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_id: str
    title: str
    association: InspectionAssociation
    provider: str | None = None
    feature_id: str | None = None
    fields: list[InspectionField] = Field(
        default_factory=lambda: list[InspectionField]()
    )
    source_url: str | None = None
    freshness: str | None = None
    stale: bool = False
    warnings: list[str] = Field(default_factory=lambda: list[str]())
    geometry: dict[str, Any] | None = None


###############################################################################
class OverlayInstance(BaseModel):
    """Stable capability instance rendered on a map at one scoped location."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    capability_id: str
    label: str
    provider: str
    overlay_type: str
    rendering_mode: str
    scope_key: str = "global"
    scope: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    resolved_location: ResolvedLocation | None = None
    viewport: dict[str, Any] | None = None
    visible: bool = True
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    render_variant: dict[str, str | None] = Field(
        default_factory=lambda: dict[str, str | None]()
    )
    descriptor: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    inspections: list[MapInspection] = Field(
        default_factory=lambda: list[MapInspection]()
    )


###############################################################################
class OverlayCollectionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = "active-map"
    revision: int = Field(default=0, ge=0)
    instances: list[OverlayInstance] = Field(
        default_factory=lambda: list[OverlayInstance]()
    )


###############################################################################
class OverlayMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = "active-map"
    revision: int
    added_instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    removed_instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    updated_instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    unmatched_selectors: list[str] = Field(default_factory=lambda: list[str]())
    ambiguous_selectors: list[str] = Field(default_factory=lambda: list[str]())
    clarification: str | None = None


###############################################################################
class LocationSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_location: ResolvedLocation
    action_id: str
    time_mode: TimeMode = "current"
    basemap_id: str
    overlay_ids: list[str] = Field(default_factory=lambda: list[str]())
    provider_layer_selections: list[ProviderLayerSelection] = Field(
        default_factory=lambda: list[ProviderLayerSelection]()
    )
    viewport: ViewportPolicy
    presentation: PresentationPolicy = Field(default_factory=PresentationPolicy)
    viewport_intent: ViewportIntent | None = None
    poi_categories: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class MapSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    resolved_location: ResolvedLocation
    basemap_id: str
    overlay_ids: list[str] = Field(default_factory=lambda: list[str]())
    viewport: ViewportPolicy
    generated_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, object] = Field(default_factory=lambda: dict[str, object]())
    center: dict[str, float | None] | None = None
    bounds: list[float] | None = None
    basemap: dict[str, object] | None = None
    overlays: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    requested_overlay_ids: list[str] = Field(default_factory=lambda: list[str]())
    rendered_overlay_ids: list[str] = Field(default_factory=lambda: list[str]())
    failed_overlays: list[dict[str, str]] = Field(
        default_factory=lambda: list[dict[str, str]]()
    )
    compliance_warnings: list[str] = Field(default_factory=lambda: list[str]())
    overlay_collection_revision: int = Field(default=0, ge=0)
    overlay_collection: OverlayCollectionState | None = None
    inspections: list[MapInspection] = Field(
        default_factory=lambda: list[MapInspection]()
    )


###############################################################################
class GeospatialCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    providers: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    basemaps: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    overlays: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    cameras: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    transit: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    tools: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
