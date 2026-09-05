# Geospatial Provider and Tool Inventory

Generated: `2026-09-05T07:08:26.104444+00:00`

## Counts

| Item | Count |
| --- | ---: |
| manifests | 86 |
| providers | 39 |
| direct_tools | 4 |
| llm_native_tools | 5 |
| runtime_profiles | 68 |

## Provider Health Matrix

| Provider | Status | Auth | Adapter | Catalog manifests | Live check |
| --- | --- | --- | --- | ---: | --- |
| `arcgis` | active | required | yes | 2 | not_sampled |
| `cartodb_tiles` | active_rendering_only | none | rendering/catalog-only | 1 | not_sampled |
| `census` | active | none | yes | 5 | not_sampled |
| `data_europa` | catalog_only | none | rendering/catalog-only | 1 | not_sampled |
| `eea` | active | none | yes | 2 | not_sampled |
| `esa` | active | none | yes | 2 | not_sampled |
| `eurostat` | active | none | yes | 4 | not_sampled |
| `fema` | active | none | yes | 1 | not_sampled |
| `gbif` | active | none | yes | 2 | not_sampled |
| `geoss` | catalog_only | none | rendering/catalog-only | 1 | not_sampled |
| `gibs` | active | none | yes | 13 | not_sampled |
| `google_maps` | catalog_only | required | rendering/catalog-only | 1 | not_sampled |
| `gtfs_realtime` | active | none | yes | 1 | not_sampled |
| `gtfs_static` | active | none | yes | 1 | not_sampled |
| `inspire` | catalog_only | none | rendering/catalog-only | 1 | not_sampled |
| `local_open_data` | active | none | yes | 7 | not_sampled |
| `mapillary` | runtime_only | none | yes | 0 | not_sampled |
| `mobility_database` | active | none | yes | 1 | not_sampled |
| `nasa_firms` | active | required | yes | 1 | not_sampled |
| `natural_earth` | active | none | yes | 1 | not_sampled |
| `noaa` | active | none | yes | 3 | not_sampled |
| `nominatim` | active | none | yes | 1 | not_sampled |
| `openaddresses` | active | none | yes | 1 | not_sampled |
| `openaq` | active | required | yes | 2 | not_sampled |
| `openchargemap` | active | none | yes | 1 | not_sampled |
| `openfreemap` | active_rendering_only | none | rendering/catalog-only | 2 | not_sampled |
| `openmeteo` | active | none | yes | 7 | not_sampled |
| `opentripmap` | active | required | yes | 1 | not_sampled |
| `osm_tiles` | active_rendering_only | none | rendering/catalog-only | 1 | not_sampled |
| `ourairports` | active | none | yes | 1 | not_sampled |
| `overpass` | active | none | yes | 4 | not_sampled |
| `overture` | active | none | yes | 1 | not_sampled |
| `pvgis` | active | none | yes | 2 | not_sampled |
| `rainviewer` | active | none | yes | 2 | not_sampled |
| `soilgrids` | active | none | yes | 2 | not_sampled |
| `terrain_tiles` | active_rendering_only | none | rendering/catalog-only | 1 | not_sampled |
| `tomtom` | active | required | yes | 3 | not_sampled |
| `usgs` | active | none | yes | 2 | not_sampled |
| `windy_webcams` | active | required | yes | 1 | not_sampled |

## LLM Tools

| Tool | Exposure | Provider/Handler | Status |
| --- | --- | --- | --- |
| `get_air_quality_forecast` | direct-tool-manifest | openmeteo | active |
| `get_nearby_poi` | direct-tool-manifest | overpass | active |
| `get_weather_forecast` | direct-tool-manifest | openmeteo | active |
| `location_to_coordinates` | direct-tool-manifest | nominatim | active |
| `list_geospatial_capabilities` | llm-native | capability-oriented | active |
| `describe_geospatial_capability` | llm-native | capability-oriented | active |
| `execute_geospatial_capability` | llm-native | capability-oriented | active |
| `fetch_geospatial_provider_layers` | llm-native | capability-oriented | active |
| `render_geospatial_provider_layer` | llm-native | capability-oriented | active |

## Replacement Outcomes

- `transitland_feeds` → `mobility_database_feeds`: **functional_for_metadata_discovery**. Worldwide feed metadata search through a local Mobility Database CSV snapshot.
  - No live Transitland API query path remains.
  - Catalog freshness depends on local snapshot refresh.
  - Feed-specific realtime access still requires separate agency credentials and licensing.

## Endpoint Samples

| Provider | Capability | Status | HTTP | Message |
| --- | --- | --- | ---: | --- |

## Findings

- `credentialed-live-coverage` (medium, external_gate): Credentialed live checks are skipped when optional provider keys are absent; no credentials are inferred or exposed.
- `openfreemap-rendering-provider` (resolved, fixed): Production auditing and endpoint validation now recognize MapLibre style_url as the concrete fetch path for OpenFreeMap basemaps.
