# Capability Catalog

Last updated: 2026-09-04

## Purpose

This file is the reviewable inventory of geospatial capabilities implemented by AEGIS. The runtime source of truth remains `app/resources/catalog`; avoid maintaining a second authoritative capability count in documentation because the manifest inventory evolves independently.

## Providers

| Provider | Purpose | Access |
| --- | --- | --- |
| `eea` | EU/EEA environmental overlays | public |
| `esa` | WorldCover land-use context | public |
| `gibs` | satellite and earth-observation layers | public |
| `openaq` | air-quality station observations | credentialed |
| `openmeteo` | weather, air-quality forecasts, and numeric point elevation | public for eligible non-commercial use; restricted capabilities require explicit opt-in |
| `overpass` | OpenStreetMap POI queries | public |
| `pvgis` | solar irradiation and photovoltaic estimates | public |
| `rainviewer` | precipitation radar tiles | public |
| `tomtom` | optional live traffic | credentialed |
| `openfreemap` | public MapLibre basemap styles | public |
| `mobility_database` | local GTFS and GTFS-Realtime feed metadata catalog | public |
| `census` | U.S. geometry and demographic joins | public with optional key for some APIs |
| `eurostat` | EU/EEA demographic and market indicators | public |
| `arcgis` | ArcGIS imagery and feature services | credentialed |
| `data_europa` | European open-data discovery | public |
| `geoss` | European geospatial discovery metadata | public |
| `google_maps` | optional commercial mapping services | credentialed |
| `inspire` | European INSPIRE discovery metadata | public |
| `fema` | National Flood Hazard Layer map context | public |
| `gbif` | biodiversity occurrence records | public |
| `noaa` | CONUS weather radar and observations | public |

## Basemaps

| ID | Purpose | Access |
| --- | --- | --- |
| `osm_default` | general street and place context | public |
| `osm_dark` | high-contrast dark basemap | public |
| `osm_terrain` | terrain-oriented context | public |
| `esri_world_imagery` | satellite imagery context | public |
| `openfreemap_liberty` | public Liberty vector basemap | public |
| `openfreemap_positron` | public Positron light vector basemap | public |

## Layers

Representative implemented layers include:

- `eea_noise_2019`
- `esa_worldcover`
- `IMERG_Precipitation_Rate`
- `MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual`
- `MODIS_Combined_Thermal_Anomalies_Fire`
- `MODIS_Terra_Aerosol`
- `MODIS_Terra_L3_Land_Water_Mask`
- `MODIS_Terra_Land_Surface_Temp_Day`
- `MODIS_Terra_Land_Surface_Temp_Night`
- `MODIS_Terra_NDVI_8Day`
- `OMPS_Ozone_Total_Column`
- `openaq_air_quality`
- `openmeteo_air_quality_forecast`
- `openmeteo_elevation`
- `openmeteo_weather_forecast`
- `overpass_poi_amenities`
- `overture_maps_places`
- `pvgis_solar`
- `rainviewer_precipitation_radar`
- `SRTM_Color_Index`
- `tomtom_traffic_flow`
- `VIIRS_SNPP_CorrectedReflectance_TrueColor`
- `VIIRS_SNPP_DayNightBand_ENCC`
- `census_tigerweb_hydrography`
- `census_tigerweb_demographics`
- `openmeteo_pressure_humidity_wind`
- `mobility_database_feeds`
- `eurostat_regional_demographics`
- `eurostat_housing_market`
- `fema_nfhl_flood_zones`
- `nasa_firms_active_fires`
- `noaa_radar`
- `noaa_weather_alerts`
- `noaa_coops_water_levels`
- `openchargemap_ev_charging`
- `opentripmap_tourism_pois`
- `usgs_earthquakes`
- `usgs_water_gauges`
- `gtfs_static`
- `gtfs_realtime`

## Direct Tools

| ID | Purpose | Source |
| --- | --- | --- |
| `location_to_coordinates` | resolve a place phrase to coordinates | Nominatim |
| `get_weather_forecast` | fetch weather forecast | Open-Meteo |
| `get_air_quality_forecast` | fetch air-quality forecast | Open-Meteo |
| `get_nearby_poi` | fetch nearby points of interest | Overpass |
| `render_geospatial_provider_layer` | render a provider-native layer descriptor | provider-neutral layer routing |
