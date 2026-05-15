# ORIGINAL PLAN: geographic intelligence capabilities for AEGIS

## 1. Repository and branch

Repository: `AEGIS`

## 2. Repository analysis summary

Top-level application shape:

| Area                        | Current role                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `app/client`                | Angular web client, including map preview and typed chat or map models                                       |
| `app/server`                | Python backend, agent orchestration, search execution, geospatial manifest loading, map session construction |
| `app/resources/manifests`   | Declarative basemap, overlay, provider, and runtime profile manifests                                        |
| `assets/docs`               | Project and architecture documentation                                                                       |
| `.github/workflows`         | CI workflow location                                                                                         |
| `app/client/package.json`   | Client build, test, and lint configuration                                                                   |
| `app/server/pyproject.toml` | Server dependency and test configuration                                                                     |

Documentation review order used:

1. `assets/docs/PROJECT_OVERVIEW.md`
2. `assets/docs/AGENTIC_SEARCH.md`
3. `assets/docs/CAPABILITY_MANIFESTS.md`
4. `assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md`
5. Architecture, coding, and UI standards docs where present

Architectural baseline to preserve:

| Existing concept            | Required preservation                                                                                                            |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Agentic search              | New datasets, overlays, and webcams must be used only when the agent determines they are necessary for the user request          |
| Main agent chat             | Every new geographic capability must be invokable in plain language through the main chat, not only through manual map controls  |
| Capability manifests        | New sources must be represented as capabilities with metadata, routing hints, auth requirements, reliability, and rendering type |
| Existing credential pattern | API keys must follow the existing TomTom and other paywalled provider access pattern. No hardcoded secrets                       |
| Map session model           | Server remains the source of truth for selected basemap, overlays, camera capability payloads, and metadata                      |
| Client map renderer         | Client renders only normalized map payloads emitted by the backend                                                               |

Official online references that must be recorded in the new docs and manifests:

| Source                   | Integration relevance                                                                                                                                                                                                                                                                                      |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Windy Webcams API        | Webcam capability. Official docs state that webcams include location, preview images, timelapses, and require `x-windy-api-key`; image URL tokens expire and must be refreshed when loading the page. ([api.windy.com][1])                                                                                 |
| GTFS Realtime            | Transit capability. Official docs define realtime transit updates, including trip updates, service alerts, and vehicle positions; the exchange format is Protocol Buffers over HTTP. ([Google for Developers][2])                                                                                          |
| NASA Open APIs           | Optional NASA API key handling reference where NASA API-backed endpoints are added; use the same credential management convention as other provider keys. ([api.nasa.gov][3])                                                                                                                              |
| Existing repository docs | `assets/docs/PROJECT_OVERVIEW.md`, `assets/docs/AGENTIC_SEARCH.md`, `assets/docs/CAPABILITY_MANIFESTS.md`, `assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md`                                                                                                                                                   |
| Existing geospatial code | `app/server/services/geospatial/manifest_loader.py`, `app/server/services/geospatial/runtime_registry.py`, `app/server/services/geospatial/capability_registry.py`, `app/server/services/geospatial/maps.py`, `app/client/src/app/components/map-preview.component.ts`, `app/client/src/app/core/types.ts` |

## 3. Current data layer audit

Audit basis: repository code and manifest inspection. This is a code-level integration status audit, not a live network proof. The implementation must add automated smoke tests and in-browser rendering validation to convert this into continuously verified status.

### 3.1 Fully functional or functionally complete after credential availability

| Manifest or capability                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Status                                                                                          | Reason                                                                             | Required action                                                                                                      |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `app/resources/manifests/basemaps/osm_default.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Functional                                                                                      | Direct public raster basemap path, no provider auth required                       | Add automated snapshot validation                                                                                    |
| `app/resources/manifests/basemaps/osm_dark.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Functional if tile URL resolves                                                                 | Same direct basemap model                                                          | Validate tile attribution and fallback                                                                               |
| `app/resources/manifests/basemaps/osm_terrain.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Functional if tile URL resolves                                                                 | Same direct basemap model                                                          | Validate tile attribution and fallback                                                                               |
| `app/resources/manifests/basemaps/gibs_satellite.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Functional or near functional                                                                   | Direct imagery basemap semantics                                                   | Verify provider naming, attribution, zoom limits, and tile URL correctness                                           |
| `app/resources/manifests/basemaps/geoapify_osm.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Functional only when key is configured                                                          | Credential-gated basemap                                                           | Keep optional, expose missing key state through access page                                                          |
| `app/resources/manifests/basemaps/tomtom_basic.json`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Functional only when key is configured                                                          | Credential-gated basemap                                                           | Keep optional, expose missing key state through access page                                                          |
| NASA GIBS raster overlay manifests under `app/resources/manifests/overlays`, including `VIIRS_SNPP_CorrectedReflectance_TrueColor.json`, `VIIRS_SNPP_DayNightBand_ENCC.json`, `MODIS_Terra_NDVI_8Day.json`, `MODIS_Terra_Aerosol.json`, `MODIS_Terra_Land_Surface_Temp_Day.json`, `MODIS_Terra_Land_Surface_Temp_Night.json`, `MODIS_Terra_L3_Land_Water_Mask.json`, `MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual.json`, `MODIS_Combined_Thermal_Anomalies_Fire.json`, `OMPS_Ozone_Total_Column.json`, `IMERG_Precipitation_Rate.json`, `SRTM_Color_Index.json` | Functionally wired if the manifest emits a valid tile or WMTS URL with resolved time parameters | These are raster overlays, compatible with the current map overlay rendering model | Add manifest validator for time dimension, tile matrix set, attribution, opacity, min/max zoom, and no-data behavior |

### 3.2 Partially wired

| Manifest or capability                                                             | Status          | Reason                                                                                                               | Required fix                                                                                                         |
| ---------------------------------------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `app/resources/manifests/overlays/rainviewer_precipitation_radar.json`             | Partially wired | RainViewer radar requires latest timestamp discovery before tile URL construction                                    | Add provider fetcher that calls RainViewer metadata, selects latest frame, then emits a resolved raster tile overlay |
| `app/resources/manifests/overlays/tomtom_traffic_flow.json`                        | Partially wired | Credential-gated traffic raster or vector tiles need provider-specific URL signing and graceful missing-key handling | Add TomTom provider adapter, credential status metadata, and map fallback state                                      |
| `app/resources/manifests/overlays/tomtom_incidents.json`, if present or referenced | Partially wired | Incident data is not just a tile, it is a live API feature collection                                                | Add live API fetcher, normalize incidents to GeoJSON, render as clustered symbols with popups                        |
| `app/resources/manifests/overlays/geoapify_amenities.json`                         | Partially wired | Places API output must be fetched, normalized, cached, clustered, and searched                                       | Add Geoapify Places adapter, bbox query support, category mapping, and popup metadata                                |
| `app/resources/manifests/overlays/overpass_poi_amenities.json`                     | Partially wired | Overpass requires bbox query construction, throttling, OSM tag normalization, and attribution                        | Add Overpass adapter, rate limiting, query templates by amenity class, and cached GeoJSON                            |
| `app/resources/manifests/overlays/openmeteo_weather_forecast.json`                 | Partially wired | Point or grid forecast API is not a direct overlay by itself                                                         | Add viewport sampling strategy, cache per geohash and time, render station or sampled grid symbols                   |
| `app/resources/manifests/overlays/openmeteo_air_quality_forecast.json`             | Partially wired | Same issue as weather forecast, plus pollutant styling                                                               | Add pollutant-specific normalization, thresholds, legends, and sampled grid rendering                                |
| `app/resources/manifests/overlays/openmeteo_pressure_humidity_wind.json`           | Partially wired | Weather variables need sampled point grid or vector arrows                                                           | Add viewport sampler, vector-arrow styling, legends, and time selector                                               |
| `app/resources/manifests/overlays/openaq_air_quality.json`                         | Partially wired | API-backed observations must be fetched and normalized into map features                                             | Add OpenAQ provider adapter, station and measurement cache, pollutant filters                                        |
| `app/resources/manifests/overlays/census_tigerweb_demographics.json`               | Partially wired | TIGERweb geometry and Census data need joining, simplification, and styling                                          | Add Census geometry fetcher, ACS data fetcher, join key handling, choropleth renderer                                |
| `app/resources/manifests/overlays/census_tigerweb_hydrography.json`                | Partially wired | Feature service must be queried by bbox and normalized                                                               | Add ArcGIS REST FeatureServer adapter and style by hydrology type                                                    |
| `app/resources/manifests/overlays/eea_noise_2019.json`                             | Partially wired | Likely static or service-backed European dataset, no generic ingestion path yet                                      | Add downloadable or WMS ingestion path, cache metadata, and region gating                                            |
| `app/resources/manifests/overlays/esa_worldcover.json`                             | Partially wired | Raster source must be exposed as tiles or preprocessed locally                                                       | Prefer official raster tile source if available, otherwise implement static raster ingestion and tiling              |
| `app/resources/manifests/overlays/pvgis_solar.json`                                | Partially wired | PVGIS is a point or area API, not a ready overlay                                                                    | Add viewport sampler or clicked-point analysis capability, do not expose as full overlay until tiling exists         |

### 3.3 Broken or unreliable as current map overlays

| Manifest or capability                                                                                      | Status                    | Why unreliable                                                                | Required fix                                                                                                               |
| ----------------------------------------------------------------------------------------------------------- | ------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `app/resources/manifests/overlays/eurostat_housing_market.json`                                             | Broken as overlay         | Eurostat statistical datasets need geospatial boundary joins before rendering | Convert to cached statistical dataset joined to NUTS boundaries, then render choropleth                                    |
| `app/resources/manifests/overlays/eurostat_regional_demographics.json`                                      | Broken as overlay         | Same boundary join problem                                                    | Add NUTS geometry ingestion and join normalization                                                                         |
| `app/resources/manifests/overlays/fred_regional_market_indicators.json`                                     | Broken as overlay         | FRED is statistical time series, not geospatial geometry                      | Convert to metadata plus geocoded region join where region identifiers are reliable; otherwise remove from overlay catalog |
| Any API-backed manifest that returns tabular JSON but lacks geometry                                        | Broken as visible overlay | The client cannot reliably render non-geographic responses                    | Add `renderingMode: metadata-only`, `search-index`, or boundary join pipeline                                              |
| Any manifest missing `license`, `attribution`, `auth`, `format`, `updateFrequency`, or `sourceOfficialDocs` | Unreliable                | Long-term maintenance and legal compliance are under-specified                | Add schema validation and fail CI if required metadata is missing                                                          |
| Any credential-gated manifest without access page linkage                                                   | Unreliable                | User cannot make the capability operational from the app                      | Add provider access metadata and missing-credential UI state                                                               |

## 4. Core design decision

Treat geographic data, live webcams, traffic cameras, public camera networks, datasets, raster overlays, vector overlays, and searchable POIs as agentic capabilities.

Do not treat everything as a passive layer.

Implement the following capability kinds:

| Capability kind     | Meaning                                                                     | Example                                      |
| ------------------- | --------------------------------------------------------------------------- | -------------------------------------------- |
| `basemap`           | Base map source                                                             | OSM, TomTom, GIBS imagery                    |
| `raster-overlay`    | Tile, WMS, or WMTS overlay                                                  | NASA GIBS, RainViewer, FEMA flood tiles      |
| `vector-overlay`    | Live or cached features rendered on map                                     | Earthquakes, traffic incidents, EV chargers  |
| `search-index`      | Searchable POI or dataset index                                             | Amenities, schools, hospitals, cameras       |
| `camera-network`    | Webcam or traffic camera capability with metadata and optional preview      | Windy Webcams, DOT cameras                   |
| `dataset-ingestion` | Downloaded or cached dataset pipeline                                       | Census, Natural Earth, Overture, GTFS static |
| `analysis-tool`     | Point, bbox, route, or area analysis                                        | PVGIS solar estimate, elevation lookup       |
| `metadata-only`     | Link and metadata only, no embedding or rendering when licensing forbids it | Restricted webcams, paid datasets            |

Agentic use rule:

The main agent must select a capability only when the user request benefits from it. Examples:

| Plain language request                                          | Agent capability selection                        |
| --------------------------------------------------------------- | ------------------------------------------------- |
| “Show webcams near the pass before I drive.”                    | `camera-network`, traffic cameras, weather, roads |
| “Find hospitals, shelters, and flood zones near this address.”  | amenities, emergency POIs, FEMA flood, geocoder   |
| “Is smoke or fire affecting this route?”                        | NASA FIRMS, air quality, weather, roads           |
| “Show transit disruptions near the station.”                    | GTFS realtime, stops, routes, alerts              |
| “Overlay demographic and parcel context for this neighborhood.” | Census, parcels where available, boundaries       |
| “What public cameras can confirm beach conditions?”             | webcams, tourism cameras, weather, official links |

Manual layer toggles stay available, but the default user path must be natural language through the main chat.

## 5. Data model and manifest schema changes

Modify `app/server/domain/geographics.py`.

Add or extend typed models:

```python
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

class CameraFeature(BaseModel):
    id: str
    name: str
    provider: str
    camera_type: str
    latitude: float
    longitude: float
    last_update_time: datetime | None
    preview_image_url: str | None
    official_url: str
    embed_url: str | None
    embedding_allowed: bool
    stale: bool
    metadata: dict[str, Any]
```

Add required manifest fields to every manifest in `app/resources/manifests`:

```json
{
  "capabilityKind": "raster-overlay",
  "renderingMode": "wmts",
  "sourceOfficialDocs": ["..."],
  "license": {
    "name": "...",
    "url": "...",
    "attributionRequired": true,
    "commercialUse": "allowed|restricted|unknown",
    "embeddingAllowed": "yes|no|metadata-only|unknown"
  },
  "auth": {
    "type": "none|api-key|oauth|token-header|paid-or-gated",
    "providerKey": "windy_webcams",
    "required": false,
    "accessPageProviderId": "windy_webcams"
  },
  "agenticUse": {
    "defaultEnabled": false,
    "manualToggle": true,
    "plannerHints": ["webcam", "road condition", "visual confirmation"],
    "requiredUserIntent": ["visual_status", "travel_condition"],
    "avoidWhen": ["general chat", "no geographic context"]
  },
  "reliability": {
    "status": "functional|partial|broken|disabled|unknown",
    "lastAudited": "YYYY-MM-DD",
    "knownLimitations": []
  },
  "cachePolicy": {
    "mode": "none|memory|disk|database|preprocessed",
    "ttlSeconds": 300,
    "staleWhileRevalidateSeconds": 3600
  },
  "normalization": {
    "geometryPath": "...",
    "idPath": "...",
    "timestampPath": "...",
    "fieldMap": {}
  }
}
```

## 6. Files to modify

| File                                                     | Required changes                                                                                                                                          |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/resources/manifests/index.json`                     | Add source catalog version, manifest schema version, capability grouping, and health status summary                                                       |
| `app/resources/manifests/runtime_profiles.json`          | Add capability-kind routing and runtime profiles for `default`, `geoint`, `webcam`, `transit`, `hazards`, `environment`, `demographics`, `infrastructure` |
| `app/resources/manifests/basemaps/*.json`                | Add required license, attribution, auth, source docs, status, zoom, and fallback fields                                                                   |
| `app/resources/manifests/overlays/*.json`                | Convert every existing overlay to schema v2 and classify as `raster-overlay`, `vector-overlay`, `search-index`, `analysis-tool`, or `metadata-only`       |
| `app/server/domain/geographics.py`                       | Add capability, layer, cache, camera, and health models                                                                                                   |
| `app/server/services/geospatial/manifest_loader.py`      | Validate schema v2, reject missing required fields in strict mode, emit migration warnings in dev mode                                                    |
| `app/server/services/geospatial/runtime_registry.py`     | Route capabilities by kind, health, auth state, and planner hints                                                                                         |
| `app/server/services/geospatial/capability_registry.py`  | Add `camera-network`, `dataset-ingestion`, and `analysis-tool` capability registration                                                                    |
| `app/server/services/geospatial/maps.py`                 | Emit normalized map sessions with resolved basemap, resolved overlays, vector payload URLs, camera payload URLs, and attribution                          |
| `app/server/services/search/orchestrator.py`             | Allow the agent to select geospatial capabilities based on intent, location, bbox, freshness needs, and cost                                              |
| `app/server/services/agent/manifest_intent_resolver.py`  | Add manifest matching for webcam, traffic camera, transit, hazards, environment, amenities, infrastructure, demographics                                  |
| `app/server/services/agent/policy_engine.py`             | Add cost, auth, privacy, freshness, and “only when necessary” decision gates                                                                              |
| `app/client/src/app/core/types.ts`                       | Add TypeScript types matching schema v2, camera features, layer health, and rendering modes                                                               |
| `app/client/src/app/components/map-preview.component.ts` | Render camera points, clustered points, vector tiles, GeoJSON, WMS, WMTS, raster tiles, choropleths, and metadata-only states                             |
| `assets/docs/PROJECT_OVERVIEW.md`                        | Add geographic intelligence platform scope                                                                                                                |
| `assets/docs/AGENTIC_SEARCH.md`                          | Add rule that geographic capabilities are agent-selected by need                                                                                          |
| `assets/docs/CAPABILITY_MANIFESTS.md`                    | Document schema v2                                                                                                                                        |
| `assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md`            | Add new optional provider credentials and access steps                                                                                                    |

## 7. Files to create

### 7.1 Backend geospatial services

Create:

```text
app/server/services/geospatial/layer_auditor.py
app/server/services/geospatial/provider_registry.py
app/server/services/geospatial/cache.py
app/server/services/geospatial/normalizers.py
app/server/services/geospatial/rendering.py
app/server/services/geospatial/tiler.py
app/server/services/geospatial/search_index.py
app/server/services/geospatial/attribution.py
app/server/services/geospatial/source_health.py
```

### 7.2 Provider clients

Create:

```text
app/server/services/geospatial/providers/base.py
app/server/services/geospatial/providers/arcgis_rest.py
app/server/services/geospatial/providers/nasa_gibs.py
app/server/services/geospatial/providers/rainviewer.py
app/server/services/geospatial/providers/tomtom.py
app/server/services/geospatial/providers/geoapify.py
app/server/services/geospatial/providers/overpass.py
app/server/services/geospatial/providers/openmeteo.py
app/server/services/geospatial/providers/openaq.py
app/server/services/geospatial/providers/windy_webcams.py
app/server/services/geospatial/providers/gtfs_static.py
app/server/services/geospatial/providers/gtfs_realtime.py
app/server/services/geospatial/providers/census.py
app/server/services/geospatial/providers/usgs.py
app/server/services/geospatial/providers/noaa.py
app/server/services/geospatial/providers/fema.py
app/server/services/geospatial/providers/nrel.py
app/server/services/geospatial/providers/openchargemap.py
app/server/services/geospatial/providers/natural_earth.py
app/server/services/geospatial/providers/overture.py
app/server/services/geospatial/providers/osm.py
app/server/services/geospatial/providers/mapillary.py
app/server/services/geospatial/providers/local_open_data.py
```

### 7.3 API endpoints

Create or extend:

```text
app/server/api/geospatial.py
app/server/api/geospatial_layers.py
app/server/api/geospatial_cameras.py
app/server/api/geospatial_sources.py
```

Required endpoints:

```text
GET /api/geospatial/capabilities
GET /api/geospatial/layers
GET /api/geospatial/layers/{layer_id}/health
GET /api/geospatial/layers/{layer_id}/features?bbox=&zoom=&time=
GET /api/geospatial/cameras?bbox=&provider=&camera_type=
GET /api/geospatial/cameras/{camera_id}
GET /api/geospatial/sources/{provider_id}/credential-status
POST /api/geospatial/audit
```

### 7.4 Client UI

Create:

```text
app/client/src/app/components/layer-catalog.component.ts
app/client/src/app/components/layer-catalog.component.html
app/client/src/app/components/layer-catalog.component.scss
app/client/src/app/components/camera-popup.component.ts
app/client/src/app/components/camera-popup.component.html
app/client/src/app/components/source-health-badge.component.ts
app/client/src/app/components/source-health-badge.component.html
app/client/src/app/services/geospatial-layer.service.ts
app/client/src/app/services/geospatial-camera.service.ts
```

### 7.5 Tests

Create:

```text
app/server/tests/geospatial/test_manifest_schema_v2.py
app/server/tests/geospatial/test_layer_auditor.py
app/server/tests/geospatial/test_provider_registry.py
app/server/tests/geospatial/test_camera_normalization.py
app/server/tests/geospatial/test_agentic_geospatial_selection.py
app/server/tests/geospatial/test_geospatial_cache.py
app/server/tests/geospatial/test_geospatial_api_contracts.py
app/client/src/app/components/map-preview.component.spec.ts
app/client/src/app/components/layer-catalog.component.spec.ts
app/client/e2e/geospatial-layers.spec.ts
app/client/e2e/geospatial-webcams.spec.ts
```

## 8. Existing layer remediation plan

### Step 1, Add manifest audit command

Create `app/server/services/geospatial/layer_auditor.py`.

Implement:

```python
def audit_all_manifests(strict: bool = False) -> LayerAuditReport:
    ...
```

Validation rules:

1. Every manifest must load.
2. Every manifest must declare `capabilityKind`.
3. Every renderable layer must declare `renderingMode`.
4. Every external source must declare `sourceOfficialDocs`.
5. Every source must declare license and attribution.
6. Every API-key source must declare `auth.providerKey`.
7. Every source must declare cache policy.
8. Every source must declare expected geometry model.
9. Every layer must be classified as `functional`, `partial`, `broken`, `disabled`, or `unknown`.
10. CI must fail on missing schema v2 fields after migration is complete.

Expose this through:

```text
python -m app.server.services.geospatial.layer_auditor --strict
```

### Step 2, Convert basemaps

Update:

```text
app/resources/manifests/basemaps/osm_default.json
app/resources/manifests/basemaps/osm_dark.json
app/resources/manifests/basemaps/osm_terrain.json
app/resources/manifests/basemaps/gibs_satellite.json
app/resources/manifests/basemaps/geoapify_osm.json
app/resources/manifests/basemaps/tomtom_basic.json
```

Add:

```json
{
  "capabilityKind": "basemap",
  "renderingMode": "xyz",
  "agenticUse": {
    "defaultEnabled": true,
    "manualToggle": true,
    "plannerHints": ["map", "base map", "satellite", "terrain"]
  }
}
```

For `geoapify_osm.json` and `tomtom_basic.json`, set:

```json
{
  "auth": {
    "type": "api-key",
    "providerKey": "geoapify",
    "required": true,
    "accessPageProviderId": "geoapify"
  }
}
```

or:

```json
{
  "auth": {
    "type": "api-key",
    "providerKey": "tomtom",
    "required": true,
    "accessPageProviderId": "tomtom"
  }
}
```

### Step 3, Convert NASA GIBS overlays

Update all NASA GIBS manifests under:

```text
app/resources/manifests/overlays/
```

For each GIBS layer, add:

```json
{
  "capabilityKind": "raster-overlay",
  "renderingMode": "wmts",
  "auth": { "type": "none", "required": false },
  "cachePolicy": { "mode": "none", "ttlSeconds": 0 },
  "agenticUse": {
    "defaultEnabled": false,
    "manualToggle": true,
    "plannerHints": ["satellite", "imagery", "fire", "aerosol", "precipitation", "vegetation", "terrain"]
  }
}
```

Fixes:

1. Resolve any `{time}` parameter before the client receives the layer.
2. Add a default date strategy per layer:

   * Daily imagery: latest known available date minus provider latency buffer.
   * Annual land cover: latest static year.
   * SRTM: static.
3. Add legends where applicable.
4. Add no-data opacity handling.
5. Add snapshot tests for at least one visible tile per layer family.

### Step 4, Fix RainViewer

Modify:

```text
app/resources/manifests/overlays/rainviewer_precipitation_radar.json
app/server/services/geospatial/providers/rainviewer.py
```

Implement:

1. Fetch RainViewer radar metadata.
2. Select latest valid frame.
3. Resolve tile URL server-side.
4. Emit `raster-overlay`.
5. Cache metadata for 5 minutes.
6. If unavailable, return stale cached frame with warning.
7. If no cached frame exists, return graceful empty layer state.

### Step 5, Fix TomTom traffic flow and incidents

Modify:

```text
app/resources/manifests/overlays/tomtom_traffic_flow.json
app/server/services/geospatial/providers/tomtom.py
assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md
```

Implement:

1. Use existing TomTom credential provider key.
2. Do not expose raw keys in client-visible URLs unless the existing app pattern already permits browser-side keys.
3. Prefer backend proxy endpoint for requests requiring protected secrets.
4. Add missing-key state:

   * layer visible in catalog
   * disabled toggle
   * “Connect TomTom access” action
5. Add traffic flow raster rendering.
6. Add traffic incidents as clustered vector features if incident manifest exists or is added.

### Step 6, Fix Geoapify and Overpass amenities

Modify:

```text
app/resources/manifests/overlays/geoapify_amenities.json
app/resources/manifests/overlays/overpass_poi_amenities.json
app/server/services/geospatial/providers/geoapify.py
app/server/services/geospatial/providers/overpass.py
app/server/services/geospatial/normalizers.py
```

Implement normalized POI schema:

```python
class PoiFeature(BaseModel):
    id: str
    name: str | None
    category: str
    source: str
    latitude: float
    longitude: float
    address: str | None
    opening_hours: str | None
    website: str | None
    phone: str | None
    metadata: dict[str, Any]
```

Supported amenity groups:

```text
schools
hospitals
clinics
pharmacies
parks
restaurants
shops
public_toilets
drinking_water
shelters
police
fire_stations
emergency_services
ev_charging
parking
bike_parking
transit_stops
trailheads
viewpoints
campsites
beaches
heritage_sites
```

Rendering:

1. Clustered points at low zoom.
2. Individual symbols at high zoom.
3. Category filter chips.
4. Popup metadata.
5. Search index integration.

### Step 7, Fix Open-Meteo layers

Modify:

```text
app/resources/manifests/overlays/openmeteo_weather_forecast.json
app/resources/manifests/overlays/openmeteo_air_quality_forecast.json
app/resources/manifests/overlays/openmeteo_pressure_humidity_wind.json
app/server/services/geospatial/providers/openmeteo.py
```

Implement:

1. `analysis-tool` for clicked-point weather.
2. `vector-overlay` for viewport sampled grid.
3. Cache by rounded bbox, zoom, variables, and forecast hour.
4. Render:

   * weather station or sampled grid points
   * wind arrows
   * pollutant symbols
   * popup with variables and timestamp
5. Add time slider only after backend supports temporal queries.

### Step 8, Fix OpenAQ

Modify:

```text
app/resources/manifests/overlays/openaq_air_quality.json
app/server/services/geospatial/providers/openaq.py
```

Implement:

1. Fetch locations by bbox.
2. Fetch latest measurements for visible stations.
3. Normalize pollutant values and units.
4. Cache station metadata longer than measurement data.
5. Render station dots with pollutant-specific colors.
6. Add filters for `pm25`, `pm10`, `no2`, `o3`, `so2`, `co`.

### Step 9, Fix Census, Eurostat, and FRED

Modify:

```text
app/resources/manifests/overlays/census_tigerweb_demographics.json
app/resources/manifests/overlays/eurostat_housing_market.json
app/resources/manifests/overlays/eurostat_regional_demographics.json
app/resources/manifests/overlays/fred_regional_market_indicators.json
app/server/services/geospatial/providers/census.py
app/server/services/geospatial/normalizers.py
```

Rules:

1. Census TIGERweb can be a vector overlay when geometry is available.
2. ACS or Census tabular data must be joined to TIGER geometry before rendering.
3. Eurostat datasets must be joined to NUTS boundaries before rendering.
4. FRED must not be shown as a map overlay unless a reliable geographic join exists.
5. If a join is unavailable, classify as `metadata-only` or `search-index`, not `vector-overlay`.

Rendering:

1. Choropleth.
2. Legend.
3. Source, vintage, and margin of error fields where available.
4. Region popup with metric, date, and source.

### Step 10, Fix ESA WorldCover and EEA Noise

Modify:

```text
app/resources/manifests/overlays/esa_worldcover.json
app/resources/manifests/overlays/eea_noise_2019.json
app/server/services/geospatial/providers/arcgis_rest.py
app/server/services/geospatial/tiler.py
```

Implement:

1. Prefer official hosted tile, WMS, or WMTS service.
2. If only downloadable data exists:

   * download to configured data cache
   * verify checksum if published
   * normalize projection to EPSG:3857 or EPSG:4326
   * build PMTiles or vector tiles for client delivery
3. Add clear attribution.
4. Add region availability constraints.

### Step 11, Fix PVGIS

Modify:

```text
app/resources/manifests/overlays/pvgis_solar.json
app/server/services/geospatial/providers/pvgis.py
```

If no provider file exists, create it.

Classify as:

```json
{
  "capabilityKind": "analysis-tool",
  "renderingMode": "metadata-only"
}
```

Do not present PVGIS as a full overlay until a reliable tiling or sampling strategy is implemented.

Agent behavior:

| User request                               | Behavior                                                                            |
| ------------------------------------------ | ----------------------------------------------------------------------------------- |
| “Solar potential here”                     | Query clicked point or resolved address                                             |
| “Compare solar potential across this area” | Sample bounded grid only after user confirms area or after agent has a bounded bbox |
| “Show solar layer everywhere”              | Explain bounded analysis is available, not global continuous overlay                |

## 9. New geographic intelligence source catalog

Implement in ordered batches. Every source must be optional unless public, unauthenticated, license-compatible, and technically reliable.

### Batch A, foundational renderable public layers

| Source                      | Capability kind                       | Access                                                 | Storage and cache                | Rendering                      |
| --------------------------- | ------------------------------------- | ------------------------------------------------------ | -------------------------------- | ------------------------------ |
| NASA GIBS                   | `raster-overlay`                      | Public WMTS or tile service, no secret for GIBS layers | No local cache initially         | Raster overlay                 |
| RainViewer                  | `raster-overlay`                      | Public metadata and tiles                              | 5 minute metadata cache          | Radar raster                   |
| USGS Earthquake GeoJSON     | `vector-overlay`                      | Public GeoJSON feeds                                   | 1 to 5 minute cache              | Clustered points               |
| NASA FIRMS                  | `vector-overlay` or `raster-overlay`  | API-key or token depending endpoint                    | 15 to 60 minute cache            | Fire points or heat overlay    |
| NOAA nowCOAST or NWS alerts | `raster-overlay` and `vector-overlay` | Public official services                               | 5 to 15 minute cache             | Weather alerts, radar, watches |
| FEMA NFHL                   | `raster-overlay` or `vector-overlay`  | Official FEMA services                                 | 1 day metadata cache             | Flood hazard overlay           |
| Natural Earth               | `dataset-ingestion`                   | Public downloads                                       | Static preprocessed vector tiles | Boundaries, places, admin      |

### Batch B, POIs and amenities

| Source                      | Capability kind                  | Access                                 | Storage and cache           | Rendering                 |
| --------------------------- | -------------------------------- | -------------------------------------- | --------------------------- | ------------------------- |
| OpenStreetMap Overpass      | `search-index`, `vector-overlay` | Public, throttle required              | Bbox cache, TTL by category | Clustered POIs            |
| Geoapify Places             | `search-index`, `vector-overlay` | API key                                | Bbox cache                  | Clustered POIs            |
| OpenTripMap                 | `search-index`                   | API key                                | POI cache                   | Tourism and attractions   |
| Wikidata geospatial queries | `search-index`, `metadata-only`  | Public, throttle required              | Query cache                 | Metadata-rich POIs        |
| GeoNames                    | `search-index`                   | Account or username depending endpoint | Query cache                 | Named geographic features |

### Batch C, webcams and public cameras as a new capability

| Source                           | Capability kind  | Access                                                                                                                  | Storage and cache                              | Rendering                                                |
| -------------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------- |
| Windy Webcams API                | `camera-network` | API key, header `x-windy-api-key`; preview tokens expire and must be refreshed when the page loads ([api.windy.com][1]) | Metadata cache 1 hour, preview refresh on load | One dot per camera, popup with preview and official link |
| Public DOT traffic camera feeds  | `camera-network` | Per agency, often public JSON, ArcGIS, XML, or 511 APIs                                                                 | Metadata cache 15 to 60 minutes                | Road camera dots                                         |
| Public transport agency cameras  | `camera-network` | Agency-specific                                                                                                         | Metadata cache per provider                    | Station or vehicle-area camera dots                      |
| Tourism webcams                  | `camera-network` | Provider-specific, many links only                                                                                      | Metadata-only when embedding is not permitted  | Camera dots with official link                           |
| Ski resort webcams               | `camera-network` | Provider-specific, often restricted embedding                                                                           | Metadata-only unless embedding permitted       | Camera dots                                              |
| Port and airport webcams         | `camera-network` | Authority-specific                                                                                                      | Metadata-only by default                       | Camera dots                                              |
| Environmental monitoring cameras | `camera-network` | Agency-specific                                                                                                         | Metadata cache                                 | Camera dots with status                                  |

Camera feature popup fields:

```text
name
provider
camera type
latitude
longitude
bearing if available
road, route, station, resort, port, or airport if available
last update time
preview image if allowed and available
staleness status
official link
embed if explicitly permitted
license or usage warning
```

Mandatory behavior:

1. Do not embed live camera feeds unless provider documentation or terms clearly permit embedding.
2. If embedding is not allowed or unknown, show only metadata, preview if allowed, and official link.
3. If preview token expires, refetch camera metadata.
4. If a camera is stale, show stale badge and do not fail the whole layer.
5. If provider key is missing, show access setup action.

### Batch D, transit and mobility

| Source                      | Capability kind                                       | Access                                                                                                     | Storage and cache                    | Rendering                     |
| --------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------ | ----------------------------- |
| GTFS Static                 | `dataset-ingestion`, `search-index`, `vector-overlay` | Agency feed downloads                                                                                      | Preprocess stops, routes, shapes     | Stops, stations, route lines  |
| GTFS Realtime               | `vector-overlay`                                      | HTTP Protobuf feeds; supports trip updates, service alerts, vehicle positions ([Google for Developers][2]) | 15 to 60 second cache by feed        | Vehicles, alerts, disruptions |
| Transitland                 | `search-index`, `dataset-ingestion`                   | API key for some usage                                                                                     | Feed registry cache                  | Feed discovery                |
| TomTom Traffic              | `raster-overlay`, `vector-overlay`                    | API key                                                                                                    | Short TTL                            | Traffic flow, incidents       |
| Open Charge Map             | `vector-overlay`, `search-index`                      | API key or public depending usage                                                                          | Daily metadata, shorter status cache | EV charging points            |
| NREL AFDC                   | `vector-overlay`, `search-index`                      | API key                                                                                                    | Daily cache                          | Alternative fuel stations     |
| Local parking APIs          | `vector-overlay`                                      | City-specific                                                                                              | TTL per provider                     | Parking lots and availability |
| Toll roads and restrictions | `dataset-ingestion`                                   | Agency-specific                                                                                            | Static or periodic                   | Lines and metadata            |

### Batch E, environmental and hazard intelligence

| Source                | Capability kind     | Access                              | Storage and cache                    | Rendering                       |
| --------------------- | ------------------- | ----------------------------------- | ------------------------------------ | ------------------------------- |
| EPA AirNow            | `vector-overlay`    | API key                             | 5 to 15 minute cache                 | AQI stations and forecast areas |
| EPA AQS               | `dataset-ingestion` | API key                             | Historical cache                     | Air quality history             |
| OpenAQ                | `vector-overlay`    | Public or API-key depending version | Station cache plus measurement cache | Pollutant station dots          |
| NOAA CO-OPS           | `vector-overlay`    | Public                              | Station cache plus observation cache | Tide and water level stations   |
| USGS Water Services   | `vector-overlay`    | Public                              | 5 to 15 minute cache                 | Stream gauges                   |
| USGS Earthquakes      | `vector-overlay`    | Public GeoJSON                      | 1 to 5 minute cache                  | Earthquake points               |
| NOAA/NWS alerts       | `vector-overlay`    | Public                              | 1 to 5 minute cache                  | Alert polygons                  |
| NASA FIRMS            | `vector-overlay`    | API key or token                    | 15 to 60 minute cache                | Active fire detections          |
| Landslide inventories | `dataset-ingestion` | Official downloads                  | Static or periodic                   | Hazard polygons                 |
| Protected areas       | `dataset-ingestion` | Official downloads or APIs          | Periodic                             | Protected area polygons         |

### Batch F, terrain, imagery, land, geology, and bathymetry

| Source                     | Capability kind                                | Access                       | Storage and cache          | Rendering                            |
| -------------------------- | ---------------------------------------------- | ---------------------------- | -------------------------- | ------------------------------------ |
| USGS 3DEP and National Map | `raster-overlay`, `analysis-tool`              | Public services              | Tile cache optional        | Elevation, hillshade                 |
| OpenTopography             | `analysis-tool`, `dataset-ingestion`           | API key for some endpoints   | Query cache                | Elevation lookup or terrain products |
| Copernicus Data Space      | `dataset-ingestion`, optional `raster-overlay` | Account or token             | Download cache             | Sentinel imagery                     |
| Sentinel Hub               | `raster-overlay`                               | Paid or credentialed         | Optional, credential-gated | Satellite raster                     |
| ESA WorldCover             | `raster-overlay` or `dataset-ingestion`        | Official dataset             | Preprocessed tiles         | Land cover                           |
| NOAA NCEI bathymetry       | `raster-overlay`, `dataset-ingestion`          | Public                       | Static tiles or downloads  | Bathymetry                           |
| GEBCO                      | `dataset-ingestion`                            | Public dataset with license  | Static tiles               | Global bathymetry                    |
| USGS geology datasets      | `dataset-ingestion`                            | Public downloads or services | Static or periodic         | Geologic maps                        |

### Batch G, boundaries, parcels, census, and demographics

| Source                             | Capability kind                       | Access                            | Storage and cache         | Rendering                    |
| ---------------------------------- | ------------------------------------- | --------------------------------- | ------------------------- | ---------------------------- |
| US Census TIGERweb                 | `vector-overlay`                      | Public                            | Geometry cache            | Boundaries                   |
| US Census ACS                      | `dataset-ingestion`, `vector-overlay` | Optional API key                  | Join to TIGER geometry    | Choropleths                  |
| Census cartographic boundary files | `dataset-ingestion`                   | Public downloads                  | Preprocessed vector tiles | Boundaries                   |
| Eurostat GISCO and statistics      | `dataset-ingestion`, `vector-overlay` | Public                            | Join to NUTS geometry     | Choropleths                  |
| Natural Earth                      | `dataset-ingestion`                   | Public downloads                  | Static vector tiles       | Admin and physical geography |
| OpenAddresses                      | `dataset-ingestion`, `search-index`   | Public downloads                  | Search index              | Address points               |
| Local parcel datasets              | `dataset-ingestion`, `vector-overlay` | County-specific, licensing varies | Periodic ingest           | Parcel polygons              |
| Postal code datasets               | `dataset-ingestion`                   | Country-specific                  | Static or periodic        | Postal polygons              |

### Batch H, infrastructure and built environment

| Source                        | Capability kind                       | Access                                   | Storage and cache        | Rendering                        |
| ----------------------------- | ------------------------------------- | ---------------------------------------- | ------------------------ | -------------------------------- |
| OSM infrastructure tags       | `vector-overlay`, `search-index`      | Overpass or extracts                     | Cached or preprocessed   | Power, pipelines, telecom, roads |
| Overture Maps                 | `dataset-ingestion`, `search-index`   | Public cloud datasets                    | Preprocessed local index | POIs, buildings, transport       |
| OurAirports                   | `dataset-ingestion`, `search-index`   | Public CSV downloads                     | Periodic                 | Airports and runways             |
| OpenAIP                       | `vector-overlay`                      | API key depending endpoint               | Cache                    | Aviation features                |
| OpenSky Network               | `vector-overlay`                      | Public or account limited                | Short cache              | Aircraft positions               |
| OpenRailwayMap or OSM railway | `raster-overlay` or `vector-overlay`  | Tile usage constraints or OSM extraction | Prefer OSM extraction    | Rail lines                       |
| Bike lanes and trails         | `dataset-ingestion`, `vector-overlay` | OSM, city, state datasets                | Cached or preprocessed   | Bike and trail networks          |
| Public works datasets         | `dataset-ingestion`                   | Local open data                          | Periodic                 | Construction and works           |

### Batch I, safety and risk layers

| Source                | Capability kind                                           | Access                                        | Storage and cache         | Rendering                                                               |
| --------------------- | --------------------------------------------------------- | --------------------------------------------- | ------------------------- | ----------------------------------------------------------------------- |
| Fire stations         | `search-index`, `vector-overlay`                          | OSM, local open data                          | Cached                    | Emergency points                                                        |
| Hospitals and clinics | `search-index`, `vector-overlay`                          | OSM, Geoapify, official health datasets       | Cached                    | Medical points                                                          |
| Shelters              | `vector-overlay`                                          | FEMA, Red Cross, local sources where official | Short cache during events | Shelter points                                                          |
| Evacuation zones      | `dataset-ingestion`                                       | Local or state emergency agencies             | Static or periodic        | Polygons                                                                |
| Evacuation routes     | `vector-overlay`                                          | Local or state official datasets              | Static or periodic        | Lines                                                                   |
| Crime statistics      | `metadata-only`, `dataset-ingestion`, or `vector-overlay` | Only legal official datasets                  | Jurisdiction-specific     | Aggregated polygons only unless public point data is explicitly allowed |
| Hazard maps           | `raster-overlay`, `vector-overlay`                        | FEMA, USGS, NOAA, state agencies              | Periodic                  | Risk overlays                                                           |

## 10. Ingestion path for downloadable datasets

Create `app/server/services/geospatial/ingestion.py`.

Every downloadable dataset manifest must define:

```json
{
  "download": {
    "sourceUrl": "...",
    "license": "...",
    "updateFrequency": "daily|weekly|monthly|quarterly|annual|static",
    "expectedFormat": "geojson|shapefile|geopackage|csv|parquet|tiff|netcdf",
    "checksumUrl": null,
    "compression": "zip|gzip|none"
  },
  "storage": {
    "rawPath": "data/geospatial/raw/{provider}/{dataset}/",
    "normalizedPath": "data/geospatial/normalized/{provider}/{dataset}/",
    "tilePath": "data/geospatial/tiles/{provider}/{dataset}/"
  },
  "normalization": {
    "targetCrs": "EPSG:4326",
    "geometryType": "Point|LineString|Polygon|Raster",
    "idField": "...",
    "fieldMap": {}
  },
  "indexing": {
    "spatialIndex": true,
    "textIndex": true,
    "vectorTile": true
  },
  "validation": {
    "minFeatureCount": 1,
    "requiredFields": [],
    "bboxMustIntersect": [-180, -90, 180, 90]
  }
}
```

Pipeline:

1. Download raw source.
2. Verify checksum if available.
3. Record source timestamp.
4. Normalize CRS.
5. Normalize field names.
6. Drop invalid geometries or repair them with logged warnings.
7. Build spatial index.
8. Build search index where text fields exist.
9. Generate vector tiles or raster tiles if needed.
10. Write manifest health record.
11. Run visual smoke test against generated layer.

## 11. Authentication and credential management

Do not create a new credential system.

Modify `assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md` and the existing access page/configuration code used by TomTom and paywalled providers.

Provider key names to add:

```text
TOMTOM_API_KEY
GEOAPIFY_API_KEY
WINDY_WEBCAMS_API_KEY
NASA_API_KEY
EPA_AIRNOW_API_KEY
NREL_API_KEY
OPENCHARGEMAP_API_KEY
TRANSITLAND_API_KEY
OPENTRIPMAP_API_KEY
SENTINEL_HUB_CLIENT_ID
SENTINEL_HUB_CLIENT_SECRET
OPENAIP_API_KEY
```

Rules:

1. Never hardcode secrets in source code.
2. Never store secrets in manifests.
3. Manifests store `providerKey`, not secret values.
4. Backend resolves credentials.
5. Client receives only:

   * capability available
   * missing credential
   * optional access setup link
   * safe public URL when allowed
6. Paid or restricted providers must be optional and disabled by default.
7. Every credential-gated layer must degrade gracefully.

## 12. Agentic selection logic

Modify:

```text
app/server/services/agent/manifest_intent_resolver.py
app/server/services/agent/policy_engine.py
app/server/services/search/orchestrator.py
app/server/services/geospatial/capability_registry.py
```

Add a geospatial capability planner stage:

```python
def select_geospatial_capabilities(
    user_query: str,
    resolved_location: LocationContext | None,
    bbox: BoundingBox | None,
    time_context: TimeContext | None,
    user_permissions: UserCapabilityAccess,
) -> list[SelectedCapability]:
    ...
```

Selection criteria:

| Criterion                                                                                                                                | Use                                                                     |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| User explicitly asks to show, map, overlay, nearby, route, live, current, satellite, camera, traffic, flood, fire, weather, demographics | Strongly consider geospatial capabilities                               |
| User asks a general factual question without location                                                                                    | Do not load layers                                                      |
| User asks for visual confirmation                                                                                                        | Consider webcam and traffic camera capability                           |
| User asks for route safety                                                                                                               | Consider traffic, incidents, weather, cameras, hazards                  |
| User asks for amenities                                                                                                                  | Consider POI search index and amenity layers                            |
| User asks for public datasets                                                                                                            | Consider source catalog and dataset ingestion                           |
| Source requires API key that is missing                                                                                                  | Return access-needed explanation and optional alternative public source |
| Source is expensive, paid, or rate-limited                                                                                               | Use only when highly relevant                                           |
| Source is stale or unhealthy                                                                                                             | Prefer healthier alternative and explain degraded status only if needed |

The agent response must be able to say:

```text
I can show flood zones, hospitals, shelters, and live traffic cameras for that area.
```

Then emit a map session with only those selected capabilities.

## 13. Map rendering plan

Modify `app/client/src/app/components/map-preview.component.ts`.

Add renderer dispatch by `renderingMode`:

```typescript
switch (layer.renderingMode) {
  case 'xyz':
  case 'raster-tile':
  case 'wmts':
  case 'wms':
    renderRasterLayer(layer);
    break;
  case 'geojson':
  case 'clustered-points':
    renderGeoJsonLayer(layer);
    break;
  case 'vector-tile':
    renderVectorTileLayer(layer);
    break;
  case 'choropleth':
    renderChoroplethLayer(layer);
    break;
  case 'camera-points':
    renderCameraLayer(layer);
    break;
  case 'metadata-only':
    renderMetadataOnlyNotice(layer);
    break;
}
```

Add:

1. Layer loading indicators.
2. Per-layer error states.
3. Per-layer attribution.
4. Legend registry.
5. Popup registry.
6. Feature clustering.
7. Empty response state.
8. Stale data badge.
9. Capability source health badge.
10. Camera preview refresh behavior.
11. Official link fallback for webcams.
12. Snapshot-safe deterministic styles for tests.

## 14. Search and discovery UX

Create `layer-catalog` UI but keep it secondary to the main chat.

Layer catalog requirements:

1. Search by natural language label.
2. Filter by category:

   * Base maps
   * Weather
   * Hazards
   * Cameras
   * Transit
   * Traffic
   * Amenities
   * Environment
   * Terrain
   * Demographics
   * Infrastructure
   * Tourism
   * Safety
3. Show health:

   * functional
   * partial
   * broken
   * missing key
   * stale
4. Show source and attribution.
5. Show required credential badge.
6. Show “Ask agent to use this” action.
7. Show manual toggle only when layer is renderable.
8. Do not show broken layers as normal toggles.

Main chat examples to support:

```text
Show traffic cameras and road incidents around Lyon.
Find public toilets and drinking water near this park.
Overlay flood zones and shelters near this address.
Show satellite fire detections and air quality around the route.
Show live transit disruptions and stops near this station.
Find webcams at nearby ski resorts.
Show demographics and schools for this neighborhood.
```

## 15. Dependency changes

Server dependencies, add only if not already present in `app/server/pyproject.toml`:

```text
httpx
pydantic
tenacity
cachetools
shapely
pyproj
geopandas, optional behind ingestion extra
rasterio, optional behind raster ingestion extra
protobuf, for GTFS Realtime
gtfs-realtime-bindings
duckdb, optional for local analytical cache
rtree or pyogrio, optional for ingestion
```

Client dependencies, add only if not already present in `app/client/package.json`:

```text
maplibre-gl, if current renderer already uses it keep existing version
supercluster, for point clustering if map library clustering is insufficient
```

Do not add heavy GIS dependencies to the default runtime unless required. Put heavy ingestion dependencies behind an optional install extra:

```toml
[project.optional-dependencies]
geospatial-ingestion = ["geopandas", "rasterio", "pyogrio", "duckdb"]
```

## 16. Ordered Codex execution plan

### Phase 1, inventory and schema

1. Read `assets/docs/PROJECT_OVERVIEW.md`.
2. Read `assets/docs/AGENTIC_SEARCH.md`.
3. Read `assets/docs/CAPABILITY_MANIFESTS.md`.
4. Read `assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md`.
5. Traverse `app/resources/manifests` and list every JSON manifest.
6. Create `app/server/services/geospatial/layer_auditor.py`.
7. Add schema v2 models to `app/server/domain/geographics.py`.
8. Update `app/server/services/geospatial/manifest_loader.py` to parse schema v2 with backward-compatible warnings.
9. Add `python -m app.server.services.geospatial.layer_auditor --strict`.
10. Add `app/server/tests/geospatial/test_manifest_schema_v2.py`.

### Phase 2, classify existing manifests

1. Update every basemap manifest.
2. Update every NASA GIBS raster overlay manifest.
3. Update RainViewer manifest as `partial` until provider fetcher is complete.
4. Update TomTom manifests as credential-gated.
5. Update Geoapify and Overpass manifests as API-backed vector overlays.
6. Update Open-Meteo manifests as analysis/vector sampling tools.
7. Update OpenAQ manifest as API-backed station overlay.
8. Update Census manifest as boundary or choropleth overlay.
9. Update Eurostat manifests as dataset plus boundary join, not direct overlays.
10. Update FRED manifest as metadata-only unless reliable geography exists.
11. Update PVGIS as analysis-tool.
12. Update `app/resources/manifests/index.json`.
13. Update `app/resources/manifests/runtime_profiles.json`.
14. Add tests proving every manifest has classification, auth, license, docs, cache policy, and health status.

### Phase 3, provider framework

1. Create `app/server/services/geospatial/providers/base.py`.
2. Create `app/server/services/geospatial/provider_registry.py`.
3. Create `app/server/services/geospatial/cache.py`.
4. Create `app/server/services/geospatial/normalizers.py`.
5. Create `app/server/services/geospatial/source_health.py`.
6. Add provider timeout, retry, and circuit breaker rules.
7. Add per-provider rate-limit configuration.
8. Add source attribution service in `app/server/services/geospatial/attribution.py`.
9. Add unit tests for provider success, empty response, timeout, bad auth, and stale cache fallback.

### Phase 4, fix existing providers

1. Implement `providers/nasa_gibs.py`.
2. Implement `providers/rainviewer.py`.
3. Implement `providers/tomtom.py`.
4. Implement `providers/geoapify.py`.
5. Implement `providers/overpass.py`.
6. Implement `providers/openmeteo.py`.
7. Implement `providers/openaq.py`.
8. Implement `providers/census.py`.
9. Implement `providers/arcgis_rest.py`.
10. Wire all provider clients into `provider_registry.py`.
11. Update `maps.py` to emit resolved, normalized render payloads.

### Phase 5, webcam capability

1. Create `providers/windy_webcams.py`.
2. Add `app/resources/manifests/cameras/windy_webcams.json`.
3. Add `app/server/api/geospatial_cameras.py`.
4. Add `CameraFeature` model.
5. Add bbox search endpoint.
6. Add camera metadata normalization.
7. Add preview token refresh behavior.
8. Add stale camera detection.
9. Add official-link-only behavior when embedding is not allowed.
10. Add camera popup client component.
11. Add camera clustered point rendering.
12. Add agent planner hints:

    * webcam
    * live view
    * road condition
    * beach condition
    * ski condition
    * airport view
    * port view
    * traffic camera
13. Add tests for:

    * missing Windy key
    * valid camera metadata
    * expired preview URL
    * metadata-only camera
    * stale camera
    * empty bbox

### Phase 6, transit and mobility

1. Create `providers/gtfs_static.py`.
2. Create `providers/gtfs_realtime.py`.
3. Add GTFS static ingestion model for stops, routes, shapes, agency, calendar.
4. Add GTFS Realtime Protobuf parser.
5. Add transit manifests:

   * `app/resources/manifests/transit/gtfs_static.json`
   * `app/resources/manifests/transit/gtfs_realtime.json`
   * `app/resources/manifests/transit/transitland_feeds.json`
6. Add support for trip updates, service alerts, and vehicle positions.
7. Add clustered stop rendering.
8. Add route line rendering.
9. Add alert popup rendering.
10. Add vehicle symbol rendering only when feed license and freshness support it.
11. Add tests with fixture GTFS static zip and fixture GTFS Realtime protobuf.

### Phase 7, hazards and environment

1. Create `providers/usgs.py`.
2. Create `providers/noaa.py`.
3. Create `providers/fema.py`.
4. Create `providers/nasa_firms.py` or add FIRMS support to `providers/nasa_gibs.py`.
5. Add manifests:

   * `app/resources/manifests/overlays/usgs_earthquakes.json`
   * `app/resources/manifests/overlays/nasa_firms_active_fires.json`
   * `app/resources/manifests/overlays/noaa_weather_alerts.json`
   * `app/resources/manifests/overlays/noaa_radar.json`
   * `app/resources/manifests/overlays/fema_nfhl_flood_zones.json`
   * `app/resources/manifests/overlays/usgs_water_gauges.json`
   * `app/resources/manifests/overlays/noaa_coops_water_levels.json`
6. Add rendering styles for hazards.
7. Add legends.
8. Add temporal freshness labels.
9. Add tests for empty, stale, and valid hazard responses.

### Phase 8, amenities, infrastructure, and tourism

1. Extend OSM and Geoapify category maps.
2. Add OpenTripMap provider and manifest.
3. Add Wikidata geospatial provider and manifest as optional metadata-rich source.
4. Add Open Charge Map provider and manifest.
5. Add NREL AFDC provider and manifest.
6. Add OurAirports ingestion manifest.
7. Add OSM infrastructure extraction profiles:

   * power
   * telecom
   * pipelines
   * rail
   * bike lanes
   * trails
   * ports
8. Add POI index update task.
9. Add unified search over POI sources.
10. Add deduplication by coordinate, name, and category.

### Phase 9, boundaries, demographics, and downloaded datasets

1. Create `app/server/services/geospatial/ingestion.py`.
2. Add Natural Earth ingestion manifest.
3. Add Census boundary ingestion manifest.
4. Add ACS join manifest.
5. Add Eurostat NUTS geometry and statistics manifests.
6. Add Overture Maps ingestion manifest as optional heavy dataset.
7. Add OpenAddresses ingestion manifest.
8. Add local parcel source template manifest.
9. Add vector tile generation support.
10. Add choropleth renderer.
11. Add dataset freshness and source vintage metadata.

### Phase 10, client integration

1. Update `app/client/src/app/core/types.ts`.
2. Update `map-preview.component.ts`.
3. Add layer catalog components.
4. Add camera popup components.
5. Add source health badges.
6. Add attribution panel.
7. Add legends.
8. Add layer loading and failure states.
9. Add search/filter/toggle behavior.
10. Ensure manual toggles never bypass agentic permissions or credential checks.
11. Add client tests.

### Phase 11, docs

1. Update `assets/docs/PROJECT_OVERVIEW.md` with geographic intelligence platform scope.
2. Update `assets/docs/AGENTIC_SEARCH.md` with agent-selected geospatial capability rules.
3. Update `assets/docs/CAPABILITY_MANIFESTS.md` with schema v2.
4. Update `assets/docs/API_ACCESS_AND_ACCOUNT_SETUP.md` with every optional provider credential.
5. Add `assets/docs/GEOSPATIAL_SOURCE_CATALOG.md`.
6. Add `assets/docs/WEBCAM_CAPABILITY.md`.
7. Add `assets/docs/GEOSPATIAL_INGESTION.md`.
8. Add `assets/docs/GEOSPATIAL_VALIDATION.md`.

## 17. Validation plan

### 17.1 Static validation

Run:

```bash
python -m app.server.services.geospatial.layer_auditor --strict
pytest app/server/tests/geospatial
npm --prefix app/client test
```

Validate:

1. All manifests parse.
2. All manifests have schema v2 fields.
3. All external sources have official docs references.
4. All credential-gated sources declare access page provider ID.
5. No secrets are present in manifests.
6. Broken layers are not exposed as normal toggleable overlays.
7. Metadata-only capabilities do not claim to render map geometry.
8. Camera capabilities never embed unless allowed.

### 17.2 Provider validation

For each provider client:

1. Mock successful response.
2. Mock empty response.
3. Mock 401 or missing credential.
4. Mock 429 rate limit.
5. Mock timeout.
6. Mock malformed payload.
7. Verify normalized output.
8. Verify cache behavior.
9. Verify attribution.
10. Verify graceful failure payload.

### 17.3 Agentic validation

Add tests to `app/server/tests/geospatial/test_agentic_geospatial_selection.py`.

Cases:

| Query                                           | Expected selected capabilities                              |
| ----------------------------------------------- | ----------------------------------------------------------- |
| “Show webcams near Donner Pass”                 | webcam capability, weather if available, roads if available |
| “Find hospitals and shelters near this address” | amenities, emergency services, shelters                     |
| “Overlay flood zones here”                      | FEMA flood zones                                            |
| “Is there smoke or fire near my route?”         | FIRMS, air quality, weather                                 |
| “Show transit disruptions near the station”     | GTFS realtime, stops, alerts                                |
| “What is the population of this county?”        | Census or demographic boundary join                         |
| “Tell me a joke”                                | no map capability                                           |
| “Search restaurants nearby”                     | POI search, not every geographic layer                      |
| “Show every possible map layer”                 | refuse indiscriminate loading, offer categories             |

### 17.4 In-app browser snapshot validation

Use the in-app browser through Playwright or the existing browser automation path.

Create:

```text
app/client/e2e/geospatial-layers.spec.ts
app/client/e2e/geospatial-webcams.spec.ts
```

Required snapshot scenarios:

1. Base map only:

   * `osm_default`
   * `osm_dark`
   * `osm_terrain`
   * `gibs_satellite`
2. Credential-gated base maps:

   * `tomtom_basic` with missing key
   * `geoapify_osm` with missing key
   * verify access-needed state and no broken map
3. Existing raster overlays:

   * VIIRS true color
   * SRTM color index
   * IMERG precipitation
   * MODIS fire anomalies
   * OMPS ozone
4. Existing live or semi-live overlays:

   * RainViewer radar
   * TomTom traffic flow, with mocked key
5. Existing API-backed vector layers:

   * Geoapify amenities, mocked
   * Overpass POIs, mocked
   * OpenAQ air quality, mocked
   * Open-Meteo weather sample grid, mocked
6. New public dataset layers:

   * USGS earthquakes
   * FEMA flood zones
   * NOAA weather alerts
   * USGS water gauges
   * Natural Earth boundaries
   * Census demographic choropleth
7. Transit:

   * GTFS stops
   * GTFS routes
   * GTFS realtime alerts
   * GTFS vehicle positions with mocked feed
8. Webcams:

   * Windy webcam dots with mocked metadata
   * DOT traffic camera dots with mocked metadata
   * popup opens
   * preview image appears when allowed
   * official link appears
   * embed absent when not allowed
   * stale camera badge appears
   * expired preview refreshes or fails gracefully
9. Empty and failed states:

   * empty bbox response
   * provider timeout
   * missing credentials
   * malformed provider response
   * stale cached response
10. Performance:

* 1,000 clustered POIs render without freezing
* 5,000 vector tile features remain usable
* camera layer clustering works at low zoom

Snapshot acceptance criteria:

1. Map remains interactive.
2. Layer is visually distinguishable.
3. Layer appears at correct approximate coordinates.
4. Popup metadata is readable.
5. Attribution is visible.
6. Failed layer does not break other layers.
7. Empty response shows no-data state.
8. Missing key shows access-needed state.
9. Webcam official link works.
10. No secret appears in browser source, logs, network URLs, or snapshots unless it is an intentionally public browser key under the existing credential pattern.

## 18. CI updates

Modify `.github/workflows/ci.yml`.

Add jobs or steps:

```bash
python -m app.server.services.geospatial.layer_auditor --strict
pytest app/server/tests/geospatial
npm --prefix app/client test
npm --prefix app/client run e2e -- geospatial-layers
npm --prefix app/client run e2e -- geospatial-webcams
```

If e2e is too slow for every PR, split:

| Workflow                           | Trigger                                 |
| ---------------------------------- | --------------------------------------- |
| Manifest schema and unit tests     | Every PR                                |
| Provider contract tests with mocks | Every PR                                |
| Browser snapshot tests with mocks  | Every PR                                |
| Live provider smoke tests          | Scheduled nightly, credentials optional |
| Heavy dataset ingestion tests      | Scheduled or manual                     |

## 19. Definition of done

This work is complete only when:

1. Every existing manifest under `app/resources/manifests` has schema v2 metadata.
2. Every existing layer is classified as functional, partial, broken, disabled, or metadata-only.
3. Broken layers are not exposed as normal working overlays.
4. The agent can invoke geographic capabilities from plain language in the main chat.
5. The agent does not load new layers unless the request justifies them.
6. Webcams and cameras are implemented as `camera-network` capabilities, not just generic data layers.
7. Camera dots render on the map with metadata popups.
8. Camera previews or embeds follow provider permission rules.
9. Credential-gated providers follow the existing access page and configuration pattern.
10. No secrets are hardcoded.
11. Static downloaded datasets have ingestion, normalization, storage, indexing, rendering, and validation paths.
12. Live APIs have fetch, normalize, cache, search, render, failure, and attribution handling.
13. The layer catalog supports discovery without replacing the main agent chat flow.
14. Automated tests cover schema, providers, agent selection, rendering, empty states, failures, and camera behavior.
15. Browser snapshots verify representative basemaps, overlays, amenity layers, public datasets, and webcam layers.
16. Documentation lists every official source, license, access method, credential requirement, and integration type.

[1]: https://api.windy.com/webcams/docs "https://api.windy.com/webcams/docs"
[2]: https://developers.google.com/transit/gtfs-realtime "https://developers.google.com/transit/gtfs-realtime"
[3]: https://api.nasa.gov/ "https://api.nasa.gov/"

# Geospatial Implementation Progress

Last updated: 2026-05-12

This document records progress against the AEGIS Geographic Intelligence completion plan. It is intentionally factual: completed work is separated from intentionally gated operational follow-up so capability status stays truthful.

## Completed In This Increment

- Added implementation-status auditing to `server.services.geospatial.layer_auditor`.
  - Reports schema validity, runtime registration, provider fetch coverage, normalizer/cache/API/client/test coverage, and placeholder statuses.
  - Fails strict audit when a functional manifest is backed by placeholder statuses.
  - Fails strict audit when placeholder-backed or metadata-only capabilities are exposed as normal manual toggles.
- Updated placeholder-backed manifests and runtime profiles so ingestion-only or partial sources are not presented as fully functional normal toggles.
- Completed provider hardening for RainViewer, TomTom, Geoapify, Overpass, Open-Meteo, OpenAQ, Windy Webcams, GTFS static/realtime, EEA, ESA, Eurostat, and NASA GIBS.
- Added optional live descriptor validation plus timeout, malformed payload, empty response, stale-cache, and stale-warning coverage where applicable for EEA WMS, ESA WMTS, Eurostat JSON-stat metadata, and NASA GIBS descriptors.
- Added Eurostat fixture-backed NUTS choropleth join coverage with `metric`, `vintage`, `marginOfError`, `source`, `legendBins`, join key metadata, and normalized `FeatureCollection` payloads.
- Kept FRED as metadata-only until a reliable geographic join exists; it is not exposed as a normal manual toggle.
- Added dataset materialization fixtures for Natural Earth, Census cartographic boundaries, OpenAddresses, Overture places, OurAirports, and a local parcel template.
  - Fixture ingestion asserts normalized GeoJSON, spatial index, text index, tile manifest, and health record generation.
- Expanded browser and scenario-catalog coverage for:
  - RainViewer radar success, stale, and empty states.
  - TomTom traffic flow and incidents.
  - Windy Webcams popup states for active preview, stale camera, no preview, and embed permission.
  - EEA WMS and ESA WMTS descriptor rendering.
  - Eurostat metadata-only and join-required states.
  - GTFS stops, routes, alerts, and vehicles.
  - 1,000 clustered POIs and 5,000-feature rendering/performance smoke coverage.
  - Attribution, stale/missing-credential badges, popups, and browser-facing secret redaction.
- Added Playwright screenshot-diff harness coverage with committed baselines:
  - `app/tests/e2e/test_geospatial_visual_regressions.py`
  - `app/tests/e2e/visual_baselines/map-canvas.png`
  - `app/tests/e2e/visual_baselines/geospatial-page.png`
- Added manifest-driven dataset materialization runner for operational non-fixture loads:
  - `python -m server.services.geospatial.materialization_runner`
  - Supports whole-catalog or filtered `--include` execution for dataset-ingestion manifests.
- Hardened agentic selection for webcams near passes, hospitals and shelters, flood zones, smoke/fire near route, transit disruptions, county population, jokes with no map intent, restaurants nearby as POI-only, and refusal of "show every layer" requests.
- Confirmed missing credentials are explained in selection metadata and public alternatives are preferred where available.
- Updated CI coverage so strict audit, backend geospatial suites, provider/API/completeness tests, client build, browser smoke tests, and optional secret-gated live smoke coverage are represented.

## Validation Evidence

The following checks passed after this increment:

- `.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict`
  - Result: 79 manifests, 0 errors.
- `.\app\server\.venv\Scripts\python.exe -m pytest -c app/server/pyproject.toml app/tests/unit/test_manifest_schema_v2.py app/tests/unit/test_provider_registry.py app/tests/unit/test_geospatial_plan_completion_surface.py app/tests/unit/test_geospatial_api_contracts.py app/tests/unit/test_agentic_geospatial_selection.py app/tests/unit/test_geospatial_implementation_completeness.py app/tests/unit/test_phase4_provider_adapters.py app/tests/unit/test_gtfs_providers.py app/tests/unit/test_regional_provider_adapters.py app/tests/unit/test_geospatial_ingestion.py app/tests/unit/services/geospatial -q`
  - Result: 110 passed, 2 third-party deprecation warnings.
- `npm run build`
  - Result: passed.
- `npm run test:e2e:geospatial`
  - Result: passed; 4 browser smoke specs succeeded and the scenario catalog validator confirmed required geospatial cases.
- `.\app\server\.venv\Scripts\python.exe -m pytest -c app/server/pyproject.toml app/tests/e2e/test_geospatial_visual_regressions.py -q`
  - Result: passed; screenshot-diff assertions matched committed visual baselines.

For Windows local runs, pytest was executed with `TEMP` and `TMP` pointed at a repository-local `.tmp_pytest` directory because the default user temp directory may be unreadable by pytest.

## Completion Status

- The implementation-critical items in the original AEGIS Geographic Intelligence completion plan are complete for the current manifest catalog and default runtime.
- Capabilities that remain partial, metadata-only, credential-gated, or ingestion-gated are intentionally classified that way and are not exposed as normal functional manual toggles.
- Live-provider execution remains optional and secret-gated in `geospatial-live-smoke.yml`; deterministic mocked contract tests cover timeout, malformed, empty, stale, attribution, and secret-redaction behavior in CI.
- Heavy production materialization beyond the small local fixtures remains an operational data-loading activity, not an implementation blocker.
- No implementation-blocking gaps remain in this completion pass.

## Second-Pass Audit Notes

The 2026-05-12 second pass checked the original plan against the current code and test surface. Follow-up implementation now closes the tooling leftovers that were still pending during the second-pass note capture:

- Playwright screenshot-diff coverage is implemented with deterministic fixture-backed baselines and CI execution in `.github/workflows/ci.yml` (`playwright-visual-regressions` job).
- Dataset materialization now includes a manifest-driven operational runner (`server.services.geospatial.materialization_runner`) so production-scale ingestion can be executed as an explicit deployment action instead of ad hoc fixture-only flow.
- Live external provider proof remains optional and secret-gated by design (`.github/workflows/geospatial-live-smoke.yml`) because it depends on credentials and external service uptime.
- The prepended original plan remains historical source material and may still contain old "partial/add provider" language; the authoritative implementation state is this progress section and the validation evidence above.

## Operational Follow-Up

Future work should be treated as operational expansion rather than completion-plan remediation:

1. Configure real provider secrets and scheduled live smoke runs in environments that are allowed to call external services.
2. Use `python -m server.services.geospatial.materialization_runner` (optionally filtered with `--include`) to materialize production-scale datasets where a deployment needs them.
3. Keep Playwright visual baselines reviewed and refreshed intentionally when UI behavior changes (`UPDATE_VISUAL_BASELINES=1`).
4. Add new source manifests only when fetch, normalize, cache, render, failure handling, attribution, and tests are included together.
