# Capability Manifests

Last updated: 2026-06-02

## Purpose

This document is the maintained technical inventory of geospatial capabilities exposed by AEGIS. The source of truth remains `app/resources/catalog`; this document mirrors the manifest catalog in a reviewable form for operators, maintainers, and UI authors.

Default capability selection prioritizes free and openly accessible providers. Geoapify and TomTom capabilities are optional and remain unavailable until users configure their own provider keys in the Access configurations page.

## Capability Loading Contract

- Providers, basemaps, overlays, and direct tools are loaded through `GeospatialManifestLoader`, `CapabilityRegistry`, and `RuntimeRegistry`.
- Capability manifests are the source of truth for agent catalog, describe, and execute operations.
- Overlay capabilities are exposed to the agent through stable catalog tools, not through generated per-overlay tool names.
- Capability IDs must remain stable because the agent executes geospatial capabilities by `capability_id`.
- Schema v2 is the only accepted manifest contract. The loader rejects manifests that omit v2 source, auth, rendering, reliability, cache, license, or normalization metadata.
- The strict auditor reports schema, provider, renderer, auth, and source-doc coverage so missing operational metadata is visible before runtime.
- Runtime availability is controlled by `runtime_profiles.json` plus credential presence.
- Credential-backed geospatial providers use the encrypted credential repository with `api_key` labels; environment variables remain a runtime fallback.
- Every capability entry must define purpose, data source, update frequency, access constraints, and dependencies.
- Every metadata object must expose ingestion traits: `official_docs_url`, `source_protocol`, `data_format`, `geometry_type`, `queryable`, `vectorizable`, `endpoint_health`, `auth_mode`, and `rate_limit_notes`.
- Queryable/vectorizable claims are reserved for GeoJSON, ArcGIS REST GeoJSON, point-insight, and time-series insight layers. Raster tile, WMS, and WMTS layers are OpenLayers-compatible but not advertised as machine-queryable vectors.
- `metadata-only` capabilities must not claim renderable geometry, map feature layers, or normal manual toggles.
- Disabled or broken layers must remain unavailable for normal manual toggles until the manifest, runtime profile, credentials, and health metadata allow rendering.
- OpenLayers-compatible source protocols are the manifest standard. The active UI renderer remains MapLibre unless an OpenLayers adapter adds unique capability.

## Providers

| Provider | Purpose | Data source | Update frequency | Access constraints | Dependencies |
| --- | --- | --- | --- | --- | --- |
| EEA (`eea`) | European Environment Agency thematic overlays, currently environmental noise. | EEA WMS services and EEA public data pages. | Static institutional datasets. | Free/public where service is available; attribution and service availability must be verified. | WMS rendering, EEA service uptime, EU/EEA coverage policy. |
| ESA (`esa`) | ESA WorldCover land-use and land-cover context. | ESA/Terrascope WMTS service. | Static release dataset. | Free/open with attribution requirements. | WMTS rendering, WorldCover layer identifiers, global coverage policy. |
| Geoapify (`geoapify`) | Optional OSM-derived basemap and amenities provider. | Geoapify Maps and Places APIs. | Static tiles and request-driven places. | Requires user-supplied Geoapify API key; disabled in the default free workflow. | Encrypted provider credential, tile/GeoJSON handling, Geoapify service terms. |
| NASA GIBS (`gibs`) | Satellite, environmental, terrain, atmosphere, and earth-observation layers. | NASA Global Imagery Browse Services WMS/WMTS endpoints. | Layer-dependent; daily, 8-day, monthly, annual, and static layers. | No API key; NASA attribution and service-aware usage required. | WMS/WMTS rendering, GIBS capabilities metadata, NASA service availability. |
| OpenAQ (`openaq`) | Air-quality station observations and measurements. | OpenAQ API and upstream station networks. | Dynamic but coverage-dependent. | Requires OpenAQ API key for current API access; source licenses and station coverage vary. | Encrypted OpenAQ credential, point-insight rendering, location radius, OpenAQ service availability. |
| Open-Meteo (`openmeteo`) | Weather and air-quality forecasts. | Open-Meteo forecast APIs. | Dynamic forecast data. | No API key in default workflow; validate non-commercial limits before production scale. | Direct tool handlers, time-series insight rendering, rate limits. |
| Overpass API (`overpass`) | OpenStreetMap POI and feature queries. | Public Overpass API instances over OSM data. | Dynamic, based on OSM and Overpass instance freshness. | No API key; respect public instance capacity, query volume, and ODbL attribution. | OSM tags, location radius, POI direct-tool handler. |
| PVGIS (`pvgis`) | Solar irradiation and photovoltaic potential estimates. | European Commission JRC PVGIS API. | Static/model-derived per-location estimates. | No API key; attribution recommended. | Point-insight rendering, location coordinates, PVGIS availability. |
| RainViewer (`rainviewer`) | Precipitation radar tiles and metadata. | RainViewer weather map metadata and tile cache. | Dynamic near-real-time radar frames. | No API key for basic use; validate tile caching and commercial terms. | Tile metadata lookup, time-indexed radar tile URL, regional radar coverage. |
| TomTom (`tomtom`) | Optional commercial road basemap and traffic flow. | TomTom Maps and Traffic APIs. | Near-real-time for traffic; provider-defined for basemap tiles. | Requires user-supplied TomTom API key; disabled in the default free workflow. | Encrypted provider credential, tile rendering, TomTom service terms. |
| U.S. Census Bureau (`census`) | U.S. demographic, boundary, and hydrography layers. | Census Data API and TIGERweb ArcGIS REST services. | Dataset/vintage-dependent. | Public access; optional Census API key for higher-volume statistical API use. | TIGERweb GeoJSON queries, Census geography joins, U.S.-only coverage. |
| Eurostat (`eurostat`) | EU/EEA demographic, housing, rent, and economic indicators. | Eurostat Statistics and JSON-stat APIs. | Dataset-dependent, provider-updated. | Free/public with attribution and dataset-specific terms. | JSON-stat parsing, regional code selection, EU/EEA coverage. |
| FRED (`fred`) | U.S. market, housing, rent, and economic time-series indicators. | Federal Reserve Economic Data API. | Series/release-calendar dependent. | Requires FRED API key; third-party series restrictions may apply. | Encrypted FRED credential, time-series retrieval, U.S. coverage. |

## Map Types

| ID | Purpose | Data source | Update frequency | Access constraints | Dependencies |
| --- | --- | --- | --- | --- | --- |
| `osm_default` | General-purpose street and place context. | OpenStreetMap raster tiles through the local OSM tile proxy. | Static tile snapshots, provider refreshed. | No API key; OSM attribution required. | MapLibre raster source, OSM proxy route, global coverage. |
| `osm_dark` | High-contrast dark visual base for bright overlays. | OpenStreetMap raster tiles styled client-side as dark. | Static tile snapshots, provider refreshed. | No API key; OSM attribution required. | MapLibre raster paint transforms, OSM proxy route. |
| `osm_terrain` | Terrain-oriented context for landform and elevation interpretation. | OpenStreetMap-derived terrain tile source in manifest metadata. | Static tile snapshots, provider refreshed. | No API key; attribution required. | MapLibre raster source, terrain tile availability. |
| `gibs_satellite` | Satellite imagery visual context for natural-color inspection. | NASA GIBS/manifest imagery tile source. | Daily imagery snapshots where available. | No API key; imagery attribution required. | MapLibre raster source, imagery tile endpoint. |
| `geoapify_osm` | Optional polished OSM Bright basemap for urban/place presentation. | Geoapify OSM Bright tile API. | Static tiles. | Requires Geoapify API key configured in Access. | Encrypted Geoapify credential, URL templating, attribution. |
| `tomtom_basic` | Optional road and transport basemap. | TomTom map tile API. | Provider-defined near-real-time tile updates. | Requires TomTom API key configured in Access. | Encrypted TomTom credential, URL templating, attribution. |

## Layers

| ID | Purpose | Data source | Update frequency | Access constraints | Dependencies |
| --- | --- | --- | --- | --- | --- |
| `eea_noise_2019` | EU/EEA environmental noise exposure context. | EEA WMS layer. | Static 2019 dataset. | No API key; EEA availability and attribution apply. | WMS renderer, EU/EEA coverage. |
| `esa_worldcover` | Global land-cover class visualization. | ESA WorldCover WMTS. | Static release dataset. | No API key; ESA attribution required. | WMTS renderer, `WORLDCOVER_2021_MAP` layer metadata. |
| `geoapify_amenities` | Optional nearby amenities and services overlay. | Geoapify Places/amenities API. | Request-driven. | Requires Geoapify API key configured in Access. | Encrypted Geoapify credential, GeoJSON/POI rendering. |
| `IMERG_Precipitation_Rate` | Precipitation intensity context. | NASA GIBS IMERG WMS layer. | 30-minute product cadence where available. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual` | Annual global land-cover classification. | NASA GIBS MODIS WMS layer. | Annual. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Combined_Thermal_Anomalies_Fire` | Active fire and thermal anomaly detection. | NASA GIBS MODIS WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Terra_Aerosol` | Aerosol optical depth and atmospheric particle load. | NASA GIBS MODIS Terra WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Terra_L3_Land_Water_Mask` | Land/water surface distinction. | NASA GIBS MODIS Terra WMS layer. | Daily/static product behavior. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Terra_Land_Surface_Temp_Day` | Daytime land surface temperature. | NASA GIBS MODIS Terra WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Terra_Land_Surface_Temp_Night` | Nighttime land surface temperature. | NASA GIBS MODIS Terra WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `MODIS_Terra_NDVI_8Day` | Vegetation condition using NDVI. | NASA GIBS MODIS Terra WMS layer. | 8-day aggregation. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `OMPS_Ozone_Total_Column` | Total-column atmospheric ozone. | NASA GIBS OMPS WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `openaq_air_quality` | Nearby air-quality observation insight. | OpenAQ API. | Dynamic station/measurement updates. | Requires OpenAQ API key; station coverage and licenses vary. | Location radius, point-insight renderer, OpenAQ service. |
| `openmeteo_air_quality_forecast` | Forecast PM and gas concentration context. | Open-Meteo Air Quality API. | Dynamic forecast model updates. | No API key in default flow; observe Open-Meteo terms. | Time-series insight renderer, location coordinates. |
| `openmeteo_weather_forecast` | Forecast temperature and precipitation context. | Open-Meteo Forecast API. | Dynamic forecast model updates. | No API key in default flow; observe Open-Meteo terms. | Time-series insight renderer, location coordinates. |
| `overpass_poi_amenities` | Nearby amenities and POI discovery. | Overpass API over OpenStreetMap. | Dynamic request-time OSM query. | No API key; respect Overpass limits and ODbL attribution. | Location radius, OSM tags, point-insight renderer. |
| `pvgis_solar` | Photovoltaic suitability and solar potential. | PVGIS API. | Static/model-derived per location. | No API key; attribution recommended. | Location coordinates, point-insight renderer. |
| `rainviewer_precipitation_radar` | Rain/storm radar visualization. | RainViewer tile metadata and radar tiles. | Near-real-time radar frames. | No API key for basic use; validate terms at scale. | Metadata fetch, tile URL resolution, MapLibre raster overlay. |
| `SRTM_Color_Index` | Terrain elevation relief. | NASA GIBS SRTM WMS layer. | Static. | No API key; NASA attribution required. | WMS renderer, GIBS SRTM layer. |
| `tomtom_traffic_flow` | Optional live road congestion and flow. | TomTom Traffic tile API. | Dynamic near-real-time traffic. | Requires TomTom API key configured in Access. | Encrypted TomTom credential, MapLibre raster overlay. |
| `VIIRS_SNPP_CorrectedReflectance_TrueColor` | Recent true-color visual earth conditions. | NASA GIBS VIIRS SNPP WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `VIIRS_SNPP_DayNightBand_ENCC` | Nighttime lights and low-light observations. | NASA GIBS VIIRS Day/Night Band WMS layer. | Monthly/static product behavior. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `census_tigerweb_hydrography` | U.S. rivers, lakes, and water features. | Census TIGERweb Hydro ArcGIS REST query with `f=geojson`. | Census/TIGERweb release-dependent. | No API key for public sampled queries; U.S. only. | Bounded GeoJSON query, MapLibre GeoJSON renderer, TIGERweb availability. |
| `census_tigerweb_demographics` | U.S. Census tract geometry for demographic joins. | Census TIGERweb Tracts/Blocks ArcGIS REST query with `f=geojson`. | Census/TIGERweb release-dependent. | No API key for public sampled queries; U.S. only. | Bounded GeoJSON query, Census geography codes, demographic-data joins. |
| `openmeteo_pressure_humidity_wind` | Pressure, humidity, wind, gust, and precipitation-probability forecast insight. | Open-Meteo Forecast API. | Dynamic forecast updates. | No API key in default flow; observe Open-Meteo terms. | Time-series insight handling, location coordinates. |
| `fred_regional_market_indicators` | U.S. housing, rent, income, and economic market indicators. | FRED API. | Series/release-calendar dependent. | Requires FRED API key. | Encrypted FRED credential, time-series insight handling. |
| `eurostat_regional_demographics` | EU/EEA population density and demographic context. | Eurostat Statistics API. | Dataset-dependent. | No API key; EU/EEA statistical coverage. | JSON-stat handling, region-code lookup. |
| `eurostat_housing_market` | EU/EEA housing, rent, and market indicator context. | Eurostat Statistics API. | Dataset-dependent. | No API key; EU/EEA statistical coverage. | JSON-stat handling, region-code lookup. |

## Source Trait Metadata

| Field | Meaning |
| --- | --- |
| `source_protocol` | Integration protocol, for example `GeoJSON`, `ArcGIS REST GeoJSON`, `WMS`, `WMTS`, `raster-tile`, or JSON insight APIs. |
| `data_format` | Runtime payload shape, for example `GeoJSON`, `JSON`, `image/png via WMS`, or image tiles. |
| `geometry_type` | Expected geometry class for queryable/vector layers, or `raster-grid` for visualization-only layers. |
| `queryable` | Indicates the layer returns structured data suitable for programmatic inspection. |
| `vectorizable` | Indicates the layer can be indexed or rendered as machine-readable features. |
| `endpoint_health` | Validation status for the manifest endpoint or representative sampled endpoint. |
| `auth_mode` | Authentication style, usually `none` or `api_key`. |
| `official_docs_url` | Maintainer-facing link to current provider documentation. |

## Direct Tools

| ID | Purpose | Data source | Update frequency | Access constraints | Dependencies |
| --- | --- | --- | --- | --- | --- |
| `location_to_coordinates` | Resolve a place phrase to latitude/longitude. | Nominatim/OpenStreetMap geocoding endpoint. | Request-driven against provider index. | No API key; respect Nominatim usage policy. | `coordinates` handler, location parser, Nominatim settings. |
| `get_weather_forecast` | Fetch weather forecast for a resolved location. | Open-Meteo Forecast API. | Dynamic forecast updates. | No API key in default flow. | `weather` handler, resolved coordinates, Open-Meteo settings. |
| `get_air_quality_forecast` | Fetch air-quality forecast for a resolved location. | Open-Meteo Air Quality API. | Dynamic forecast updates. | No API key in default flow. | `air_quality` handler, resolved coordinates, Open-Meteo settings. |
| `get_nearby_poi` | Fetch nearby points of interest. | Overpass API over OpenStreetMap. | Request-driven. | No API key; respect Overpass public instance limits and ODbL attribution. | `poi` handler, resolved coordinates, radius policy. |

## Maintenance Rules

- Additive capability work must update the manifest JSON, `runtime_profiles.json`, tests, and this document in the same change.
- Credential-required providers must remain optional unless explicitly promoted by product policy.
- Free/open alternatives should be preferred for default workflows.
- UI pages should consume `/api/maps/catalog` rather than duplicating manifest parsing logic.

## Schema V2 Required Fields

Every manifest under `app/resources/catalog` must define:

- `capabilityKind`: one of `basemap`, `raster-overlay`, `vector-overlay`, `search-index`, `camera-network`, `dataset-ingestion`, `analysis-tool`, or `metadata-only`.
- `renderingMode`: one of `xyz`, `wmts`, `wms`, `geojson`, `vector-tile`, `raster-tile`, `clustered-points`, `choropleth`, `camera-points`, or `metadata-only`.
- `sourceOfficialDocs`: official provider documentation URLs.
- `license`: name, URL, attribution requirement, commercial-use status, and embedding allowance.
- `auth`: provider auth type, provider key name, required flag, and access-page provider ID when credentials are required.
- `account_setup`: optional provider setup guide metadata consumed by the Access configurations wizard.
- `agenticUse`: planner hints, default enablement, manual-toggle policy, and avoid-when rules.
- `agenticUse.action_tags`: discovery hints returned by catalog and describe responses. They are not used to rank or select which tools the agent may call.
- `agenticUse.requiredUserAction`: optional required user action hint for gating geospatial capability use.
- `reliability`: health status, audit date, and known limitations.
- `cachePolicy`: cache mode, TTL, and stale-while-revalidate TTL.
- `normalization`: expected geometry model and field/path mapping for renderable or queryable payloads.

Additional strict rules:

- Credential-gated manifests must set both `auth.providerKey` and `auth.accessPageProviderId`.
- Manifests must never contain raw secrets, access tokens, bearer values, or concrete API keys.
- `account_setup.credential_fields` must contain access keys or tokens only, never third-party portal usernames or passwords.
- Renderable capabilities must declare a supported rendering mode and normalization geometry.
- Metadata-only and analysis-tool capabilities may expose descriptive or computed payloads, but cannot masquerade as successful empty map geometry.

Example `account_setup` block:

```json
{
  "account_setup": {
    "mode": "manual",
    "automation_supported": false,
    "automation_reason": "Third-party provider signup and key retrieval require external account, billing, MFA, CAPTCHA, or portal flows that are not stable product APIs.",
    "account_url": "https://console.cloud.google.com",
    "dashboard_url": "https://console.cloud.google.com/google/maps-apis/credentials",
    "documentation_url": "https://developers.google.com/maps/documentation/javascript/get-api-key",
    "credential_fields": [
      {
        "name": "api_key",
        "label": "API key",
        "secret": true,
        "required": true
      }
    ],
    "steps": [
      {
        "id": "create_account",
        "title": "Create or sign in to the provider account",
        "description": "Open the provider account page and complete signup or sign in."
      }
    ]
  }
}
```

Run the strict audit before merging manifest changes:

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict
```

## Reference Catalog

`app/resources/catalog/reference` stores seedable static reference data that should not live in Python constants:

- `countries.json`
- `geospatial_layers.json`
- `gibs_tile_matrix_sets.json`
- `gibs_layer_defaults.json`

Startup behavior:

- The app creates relational schema first.
- It then loads the reference catalog files.
- It seeds only empty target reference tables.
- Populated target tables are not reseeded or upserted during startup.

## Agent Catalog Contract

Agent access to manifests uses three stable native tools:

- `list_geospatial_capabilities` returns compact metadata only and must paginate deterministically. Page size is capped at 50.
- `describe_geospatial_capability` returns one full manifest descriptor plus the executable argument JSON schema.
- `execute_geospatial_capability` validates supplied arguments against the manifest schema before execution.

The agent must not depend on embeddings, semantic retrieval, `top_k` ranking, or vector indexes to decide which manifest tools are visible. Vectorized manifest data may remain available to non-agent search UI, but agent tool exposure is catalog-based.

## Account setup automation metadata

Credential-gated manifests may include an `account_setup.automation` object used by the Access settings page experimental guided setup trigger. The object is metadata only unless a provider-specific runtime explicitly implements a guided session.

Required fields:

```json
{
  "support": "agent_assisted",
  "signup_url": "https://provider.example/signup",
  "developer_portal_url": "https://provider.example/dashboard",
  "docs_url": "https://provider.example/docs",
  "required_fields": [],
  "user_action_notes": [],
  "safety_notes": [],
  "experimental": true,
  "experimental_label": "Experimental guided setup"
}
```

`support` must be one of `manual_only`, `guided_playwright`, `agent_assisted`, or `unsupported`. The metadata must never request or describe storage for provider passwords, CAPTCHA responses, 2FA codes, recovery codes, or billing credentials. Use `safety_notes` to state provider-specific boundaries such as Google Maps billing/project setup, and use `user_action_notes` to explain where the user must complete provider-controlled steps.

All experimental guided setup flows must degrade to manual instructions and official provider links when automation is unavailable, blocked, or unreliable.
