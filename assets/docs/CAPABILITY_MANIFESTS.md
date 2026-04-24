# Capability Manifests

Last updated: 2026-04-24

## Purpose

This document is the maintained technical inventory of geospatial capabilities exposed by AEGIS. The source of truth remains `AEGIS/resources/manifests`; this document mirrors the manifest catalog in a reviewable form for operators, maintainers, and UI authors.

Default capability selection prioritizes free and openly accessible providers. Geoapify and TomTom capabilities are optional and remain unavailable until users configure their own provider keys in the Access configurations page.

## Capability Loading Contract

- Providers, basemaps, overlays, and direct tools are loaded through `GeospatialManifestLoader`, `CapabilityRegistry`, and `RuntimeRegistry`.
- Runtime availability is controlled by `runtime_profiles.json` plus credential presence.
- Credential-backed geospatial providers use the encrypted credential repository with `api_key` labels; environment variables remain a runtime fallback.
- Every capability entry must define purpose, data source, update frequency, access constraints, and dependencies.

## Providers

| Provider | Purpose | Data source | Update frequency | Access constraints | Dependencies |
| --- | --- | --- | --- | --- | --- |
| EEA (`eea`) | European Environment Agency thematic overlays, currently environmental noise. | EEA WMS services and EEA public data pages. | Static institutional datasets. | Free/public where service is available; attribution and service availability must be verified. | WMS rendering, EEA service uptime, EU/EEA coverage policy. |
| ESA (`esa`) | ESA WorldCover land-use and land-cover context. | ESA/Terrascope WMTS service. | Static release dataset. | Free/open with attribution requirements. | WMTS rendering, WorldCover layer identifiers, global coverage policy. |
| Geoapify (`geoapify`) | Optional OSM-derived basemap and amenities provider. | Geoapify Maps and Places APIs. | Static tiles and request-driven places. | Requires user-supplied Geoapify API key; disabled in the default free workflow. | Encrypted provider credential, tile/GeoJSON handling, Geoapify service terms. |
| NASA GIBS (`gibs`) | Satellite, environmental, terrain, atmosphere, and earth-observation layers. | NASA Global Imagery Browse Services WMS/WMTS endpoints. | Layer-dependent; daily, 8-day, monthly, annual, and static layers. | No API key; NASA attribution and service-aware usage required. | WMS/WMTS rendering, GIBS capabilities metadata, NASA service availability. |
| OpenAQ (`openaq`) | Air-quality station observations and measurements. | OpenAQ API and upstream station networks. | Dynamic but coverage-dependent. | No configured API key required; source licenses and station coverage vary. | Point-insight rendering, location radius, OpenAQ service availability. |
| Open-Meteo (`openmeteo`) | Weather and air-quality forecasts. | Open-Meteo forecast APIs. | Dynamic forecast data. | No API key in default workflow; validate non-commercial limits before production scale. | Direct tool handlers, time-series insight rendering, rate limits. |
| Overpass API (`overpass`) | OpenStreetMap POI and feature queries. | Public Overpass API instances over OSM data. | Dynamic, based on OSM and Overpass instance freshness. | No API key; respect public instance capacity, query volume, and ODbL attribution. | OSM tags, location radius, POI direct-tool handler. |
| PVGIS (`pvgis`) | Solar irradiation and photovoltaic potential estimates. | European Commission JRC PVGIS API. | Static/model-derived per-location estimates. | No API key; attribution recommended. | Point-insight rendering, location coordinates, PVGIS availability. |
| RainViewer (`rainviewer`) | Precipitation radar tiles and metadata. | RainViewer weather map metadata and tile cache. | Dynamic near-real-time radar frames. | No API key for basic use; validate tile caching and commercial terms. | Tile metadata lookup, time-indexed radar tile URL, regional radar coverage. |
| TomTom (`tomtom`) | Optional commercial road basemap and traffic flow. | TomTom Maps and Traffic APIs. | Near-real-time for traffic; provider-defined for basemap tiles. | Requires user-supplied TomTom API key; disabled in the default free workflow. | Encrypted provider credential, tile rendering, TomTom service terms. |

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
| `openaq_air_quality` | Nearby air-quality observation insight. | OpenAQ API. | Dynamic station/measurement updates. | No API key; station coverage and licenses vary. | Location radius, point-insight renderer, OpenAQ service. |
| `openmeteo_air_quality_forecast` | Forecast PM and gas concentration context. | Open-Meteo Air Quality API. | Dynamic forecast model updates. | No API key in default flow; observe Open-Meteo terms. | Time-series insight renderer, location coordinates. |
| `openmeteo_weather_forecast` | Forecast temperature and precipitation context. | Open-Meteo Forecast API. | Dynamic forecast model updates. | No API key in default flow; observe Open-Meteo terms. | Time-series insight renderer, location coordinates. |
| `overpass_poi_amenities` | Nearby amenities and POI discovery. | Overpass API over OpenStreetMap. | Dynamic request-time OSM query. | No API key; respect Overpass limits and ODbL attribution. | Location radius, OSM tags, point-insight renderer. |
| `pvgis_solar` | Photovoltaic suitability and solar potential. | PVGIS API. | Static/model-derived per location. | No API key; attribution recommended. | Location coordinates, point-insight renderer. |
| `rainviewer_precipitation_radar` | Rain/storm radar visualization. | RainViewer tile metadata and radar tiles. | Near-real-time radar frames. | No API key for basic use; validate terms at scale. | Metadata fetch, tile URL resolution, MapLibre raster overlay. |
| `SRTM_Color_Index` | Terrain elevation relief. | NASA GIBS SRTM WMS layer. | Static. | No API key; NASA attribution required. | WMS renderer, GIBS SRTM layer. |
| `tomtom_traffic_flow` | Optional live road congestion and flow. | TomTom Traffic tile API. | Dynamic near-real-time traffic. | Requires TomTom API key configured in Access. | Encrypted TomTom credential, MapLibre raster overlay. |
| `VIIRS_SNPP_CorrectedReflectance_TrueColor` | Recent true-color visual earth conditions. | NASA GIBS VIIRS SNPP WMS layer. | Daily. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |
| `VIIRS_SNPP_DayNightBand_ENCC` | Nighttime lights and low-light observations. | NASA GIBS VIIRS Day/Night Band WMS layer. | Monthly/static product behavior. | No API key; NASA attribution required. | WMS renderer, GIBS layer availability. |

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
