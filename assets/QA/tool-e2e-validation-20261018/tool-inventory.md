# Tool inventory — 2026-10-18

Last updated: 2026-10-18

Generated from the isolated runtime's `GET /api/geospatial/capabilities` (68 executable
capabilities), the gap-only direct provider matrix ([provider-matrix.json](provider-matrix.json)),
and prior gate evidence in the [gate ledger](../../docs/validation/gate_status.md).
Statuses: prior PASS keeps its gate; *this campaign* rows cite [report.md](report.md).

## Native agent tools (`app/server/services/agent/native_tools.py`)

| Tool | Visibility | Exercised live this campaign | Result |
| --- | --- | --- | --- |
| `route_request` | internal | every run | PASS |
| `resolve_geospatial_location` | model | X-01, X-02, X-08, X-13 | PASS; Tokyo-as-city rejected (open finding F-12) |
| `discover_geospatial_capabilities` | model | X-01, X-02, X-07 | FIXED: `compare` operation, whole-phrase avoid rule, plain subject variants |
| `discover_geospatial_provider_layers` | internal | exposed in X-07 named-provider route | FIXED: named-provider add_layer now data-bearing |
| `describe_geospatial_capability` | model | all data runs | PASS |
| `execute_geospatial_capability` | model | all data runs | FIXED: label/key location_ref matching |
| `inspect_evidence` | model | T3-18 provenance (answered from saved evidence) | PASS (no re-fetch) |
| `transform_evidence` | model | not selected by the model in any run | UNRUN live (unit only) |
| `apply_map_plan` | model | all map runs | FIXED: multi-place evidence layers and union viewport |
| `search_conversation_history` | model, conditional | not required by any run | UNRUN live (unit only) |

## Catalog capabilities

| Capability | Kind | Provider | Available | Credential | Map/Text | Rendering | Prior evidence | This campaign |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `esri_world_imagery` | basemap | arcgis | yes | none | map | xyz | PASS T3-16 | — |
| `openfreemap_liberty` | basemap | openfreemap | yes | none | map | vector-tile | PASS T3-16 | — |
| `openfreemap_positron` | basemap | openfreemap | yes | none | map | vector-tile | PASS T3-16 | — |
| `osm_dark` | basemap | cartodb_tiles | yes | none | map | xyz | PASS T3-03 | — |
| `osm_default` | basemap | osm_tiles | yes | none | map | xyz | PASS T3-01 ([ledger](../../docs/validation/gate_status.md)) | — |
| `osm_terrain` | basemap | opentopomap | yes | none | map | xyz | PASS T3-03 | — |
| `census_acs_demographic_joins` | dataset-ingestion | census | yes | none | map/text | choropleth | — | normal: HTTP 200 ok; out_of_coverage: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `census_cartographic_boundaries` | dataset-ingestion | census | yes | none | map/text | vector-tile | — | normal: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `census_tigerweb_demographics` | vector-overlay | census | yes | none | map/text | choropleth | — | normal: HTTP 200 ok |
| `census_tigerweb_hydrography` | vector-overlay | census | yes | none | map | geojson | PASS T3-05 | — |
| `eea_noise_2019` | raster-overlay | eea | yes | none | map | wms | BLOCKED T3-15 (retired upstream WMS) | BLOCKED: upstream 2019 WMS retired (unchanged) |
| `esa_worldcover` | raster-overlay | esa | yes | none | map | wms | PASS T3-07 | — |
| `eurostat_housing_market` | metadata-only | eurostat | yes | none | text | metadata-only | — | normal: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `eurostat_nuts_regions` | dataset-ingestion | eurostat | yes | none | map/text | vector-tile | — | normal: HTTP 200 ok; out_of_coverage: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `eurostat_regional_demographics` | metadata-only | eurostat | yes | none | text | metadata-only | — | normal: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `fema_nfhl_flood_zones` | raster-overlay | fema | yes | none | map | raster-tile | PASS T3-07 | — |
| `gbif_species_occurrences` | vector-overlay | gbif | yes | none | map/text | clustered-points | PASS T3-14 | — |
| `IMERG_Precipitation_Rate` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `local_parcel_template` | dataset-ingestion | local_open_data | yes | none | map/text | metadata-only | — | — |
| `MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `MODIS_Combined_Thermal_Anomalies_Fire` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | FIXED: WMS 1.3.0 EXCEPTIONS error tile rendered as data (X-13); proxy re-verified |
| `MODIS_Terra_Aerosol` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `MODIS_Terra_L3_Land_Water_Mask` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `MODIS_Terra_Land_Surface_Temp_Day` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `MODIS_Terra_Land_Surface_Temp_Night` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `MODIS_Terra_NDVI_8Day` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `nasa_firms_active_fires` | vector-overlay | nasa_firms | no — Configure provider credentials in Settings under Geospatial Access. | required | map/text | clustered-points | — | no_credential: HTTP 200 missing-credential |
| `natural_earth_admin_boundaries` | dataset-ingestion | natural_earth | yes | none | text | vector-tile | — | normal: HTTP 200 ok; ocean_empty: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `noaa_coops_water_levels` | vector-overlay | noaa | yes | none | map/text | clustered-points | PASS T3-11 | — |
| `noaa_radar` | raster-overlay | noaa | yes | none | map | raster-tile | PASS T3-11 | — |
| `noaa_weather_alerts` | vector-overlay | noaa | yes | none | map/text | geojson | PASS T3-04 | PASS live X-13 valid-empty California (honestly reported) |
| `OMPS_Ozone_Total_Column` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `openaddresses_points` | dataset-ingestion | openaddresses | yes | none | map/text | clustered-points | — | normal: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `openaq_air_quality` | vector-overlay | openaq | no — Configure provider credentials in Settings under Geospatial Access. | required | map/text | clustered-points | — | no_credential: HTTP 200 missing-credential |
| `openchargemap_ev_charging` | vector-overlay | openchargemap | no — Configure an Open Charge Map API key in Settings under Geospatial Access or a local snapshot via AEGIS_OCM_SNAPSHOT_PATH. | none | map/text | clustered-points | — | no_credential: HTTP 200 missing-credential |
| `openmeteo_air_quality_forecast` | analysis-tool | openmeteo | yes | none | map/text | clustered-points | — | normal: HTTP 200 ok |
| `openmeteo_elevation` | analysis-tool | openmeteo | no — Capability is disabled. | none | map/text | clustered-points | — | FIXED: direct API bypassed restricted-use opt-in (now 403); agent path disabled by licence policy |
| `openmeteo_pressure_humidity_wind` | analysis-tool | openmeteo | yes | none | map/text | clustered-points | PASS T3-13 | — |
| `openmeteo_weather_forecast` | analysis-tool | openmeteo | yes | none | map/text | clustered-points | — | PASS live X-02/X-07/X-10 (multi-place compare, follow-up, grounded) |
| `opentripmap_tourism_pois` | search-index | opentripmap | no — Configure provider credentials in Settings under Geospatial Access. | required | map/text | clustered-points | — | no_credential: HTTP 200 missing-credential |
| `ourairports_airports` | dataset-ingestion | ourairports | yes | none | map/text | clustered-points | — | normal: HTTP 200 ok; ocean_empty: HTTP 200 ok; antimeridian: HTTP 400 bbox must be ordered west,south,east,north. (descriptor/metadata contract only; no upstream data retrieved) |
| `overpass_poi_amenities` | search-index | overpass | yes | none | map/text | clustered-points | PASS T3-12 | Routing FIXED (X-01); live retrieval BLOCKED by upstream Overpass overload (502/31 s) |
| `overpass_residential_buildings` | vector-overlay | overpass | yes | none | map | geojson | PASS T3-12 | — |
| `overture_maps_places` | dataset-ingestion | overture | no — Configure the required local or trusted source before use. | none | map/text | clustered-points | — | unconfigured_source: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `pvgis_solar` | analysis-tool | pvgis | yes | none | text | metadata-only | — | normal: HTTP 200 ok; ocean: HTTP 200 ok |
| `rainviewer_precipitation_radar` | raster-overlay | rainviewer | yes | none | map | raster-tile | PASS T3-09 | PASS live X-07 + vision runs |
| `soilgrids_soil_properties` | analysis-tool | soilgrids | yes | none | text | metadata-only | — | normal: HTTP 200 ok; ocean: HTTP 200 ok |
| `SRTM_Color_Index` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `tomtom_traffic_flow` | raster-overlay | tomtom | no — Configure provider credentials in Settings under Geospatial Access. | required | map | raster-tile | — | — |
| `tomtom_traffic_incidents` | vector-overlay | tomtom | no — Configure provider credentials in Settings under Geospatial Access. | required | map/text | clustered-points | — | no_credential: HTTP 200 missing-credential |
| `usgs_earthquakes` | vector-overlay | usgs | yes | none | map/text | clustered-points | PASS T3-02/T3-10 | PASS live X-13; valid-empty boundary Japan (vision final_check) |
| `usgs_water_gauges` | vector-overlay | usgs | yes | none | map/text | clustered-points | — | normal: HTTP 200 ok; out_of_coverage: HTTP 200 ok |
| `VIIRS_SNPP_CorrectedReflectance_TrueColor` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `VIIRS_SNPP_DayNightBand_ENCC` | raster-overlay | gibs | yes | none | map | wms | PASS T3-08 | — |
| `dot_traffic_cameras` | camera-network | local_open_data | no — Capability is disabled. | none | map | camera-points | — | — |
| `environmental_monitoring_cameras` | camera-network | local_open_data | no — Capability is disabled. | none | map | camera-points | — | — |
| `port_airport_webcams` | camera-network | local_open_data | no — Capability is disabled. | none | map | camera-points | — | — |
| `public_transport_cameras` | camera-network | local_open_data | no — Capability is disabled. | none | map | camera-points | — | — |
| `ski_resort_webcams` | camera-network | local_open_data | no — Capability is disabled. | none | map | camera-points | — | — |
| `tourism_webcams` | camera-network | local_open_data | no — Capability is disabled. | none | map | camera-points | — | — |
| `windy_webcams` | camera-network | windy_webcams | no — Configure provider credentials in Settings under Geospatial Access. | required | map | camera-points | — | — |
| `gtfs_realtime` | vector-overlay | gtfs_realtime | no — Configure the required local or trusted source before use. | none | map/text | clustered-points | PASS T4-04 (adapter only) | — |
| `gtfs_static` | dataset-ingestion | gtfs_static | no — Configure the required local or trusted source before use. | none | map/text | clustered-points | PASS T4-04 (adapter only) | unconfigured_source: HTTP 200 ok (descriptor/metadata contract only; no upstream data retrieved) |
| `mobility_database_feeds` | search-index | mobility_database | yes | none | text | metadata-only | — | normal: HTTP 200 ok |
| `get_air_quality_forecast` | analysis-tool | openmeteo | yes | none | text | metadata-only | PASS T2-05 | — |
| `get_nearby_poi` | search-index | overpass | yes | none | text | metadata-only | PASS T2-05 | — |
| `get_weather_forecast` | analysis-tool | openmeteo | yes | none | text | metadata-only | PASS T2-05 | — |
| `location_to_coordinates` | analysis-tool | nominatim | yes | none | text | metadata-only | PASS T2-05 | — |

Total catalog capabilities listed: 68. Configured geospatial credentials in the copied
canonical database: none (only the `opencode-go` model key), so every credential-gated
capability returns an honest `missing-credential` status; T4-07 remains BLOCKED.
