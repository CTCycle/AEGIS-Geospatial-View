# Capability Catalog

Last updated: 2026-08-02

## Purpose

This file is the reviewable inventory of geospatial capabilities implemented by AEGIS. The runtime source of truth remains `app/resources/catalog`.

The current catalog snapshot contains 6 basemaps, 48 overlays, 18 provider
descriptors, 4 direct tools, 7 camera networks, and 3 transit capabilities.

## Providers

| Provider | Purpose | Access |
| --- | --- | --- |
| `eea` | EU/EEA environmental overlays | public |
| `esa` | WorldCover land-use context | public |
| `geoapify` | optional OSM-derived amenities | credentialed |
| `gibs` | satellite and earth-observation layers | public |
| `openaq` | air-quality station observations | credentialed |
| `openmeteo` | weather and air-quality forecasts | public |
| `overpass` | OpenStreetMap POI queries | public |
| `pvgis` | solar irradiation and photovoltaic estimates | public |
| `rainviewer` | precipitation radar tiles | public |
| `tomtom` | optional live traffic | credentialed |
| `openfreemap` | public MapLibre basemap styles | public |
| `mobility_database` | local GTFS and GTFS-Realtime feed metadata catalog | public |
| `census` | U.S. geometry and demographic joins | public with optional key for some APIs |
| `eurostat` | EU/EEA demographic and market indicators | public |
| `fred` | U.S. economic and market indicators | credentialed |
| `arcgis` | ArcGIS imagery and feature services | credentialed |
| `data_europa` | European open-data discovery | public |
| `geoss` | European geospatial discovery metadata | public |
| `google_maps` | optional commercial mapping services | credentialed |
| `inspire` | European INSPIRE discovery metadata | public |

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
- `geoapify_amenities`
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
- `fred_regional_market_indicators`
- `eurostat_regional_demographics`
- `eurostat_housing_market`
- `fema_nfhl_flood_zones`
- `nasa_firms_active_fires`
- `noaa_radar`
- `noaa_weather_alerts`
- `nrel_afdc_alt_fuel_stations`
- `openchargemap_ev_charging`
- `opentripmap_tourism_pois`
- `usgs_earthquakes`
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
