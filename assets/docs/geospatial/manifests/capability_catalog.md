# Capability Catalog

Last updated: 2026-06-02

## Purpose

This file is the reviewable inventory of geospatial capabilities implemented by AEGIS. The runtime source of truth remains `app/resources/catalog`.

## Providers

| Provider | Purpose | Access |
| --- | --- | --- |
| `eea` | EU/EEA environmental overlays | public |
| `esa` | WorldCover land-use context | public |
| `geoapify` | optional OSM-derived basemap and amenities | credentialed |
| `gibs` | satellite and earth-observation layers | public |
| `openaq` | air-quality station observations | credentialed |
| `openmeteo` | weather and air-quality forecasts | public |
| `overpass` | OpenStreetMap POI queries | public |
| `pvgis` | solar irradiation and photovoltaic estimates | public |
| `rainviewer` | precipitation radar tiles | public |
| `tomtom` | optional road basemap and live traffic | credentialed |
| `census` | U.S. geometry and demographic joins | public with optional key for some APIs |
| `eurostat` | EU/EEA demographic and market indicators | public |
| `fred` | U.S. economic and market indicators | credentialed |

## Basemaps

| ID | Purpose | Access |
| --- | --- | --- |
| `osm_default` | general street and place context | public |
| `osm_dark` | high-contrast dark basemap | public |
| `osm_terrain` | terrain-oriented context | public |
| `gibs_satellite` | satellite imagery context | public |
| `geoapify_osm` | polished OSM Bright variant | credentialed |
| `tomtom_basic` | optional road and transport basemap | credentialed |

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
- `pvgis_solar`
- `rainviewer_precipitation_radar`
- `SRTM_Color_Index`
- `tomtom_traffic_flow`
- `VIIRS_SNPP_CorrectedReflectance_TrueColor`
- `VIIRS_SNPP_DayNightBand_ENCC`
- `census_tigerweb_hydrography`
- `census_tigerweb_demographics`
- `openmeteo_pressure_humidity_wind`
- `fred_regional_market_indicators`
- `eurostat_regional_demographics`
- `eurostat_housing_market`

## Direct Tools

| ID | Purpose | Source |
| --- | --- | --- |
| `location_to_coordinates` | resolve a place phrase to coordinates | Nominatim |
| `get_weather_forecast` | fetch weather forecast | Open-Meteo |
| `get_air_quality_forecast` | fetch air-quality forecast | Open-Meteo |
| `get_nearby_poi` | fetch nearby points of interest | Overpass |
