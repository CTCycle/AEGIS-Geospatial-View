# Geospatial Source Catalog

Last updated: 2026-05-11

## Purpose

AEGIS treats geographic data sources as manifest-backed capabilities. The single source of truth is `app/resources/manifests`; this document summarizes the current integration status.

## Implemented Capability Classes

| Kind | Current status |
| --- | --- |
| `basemap` | Schema-v2 manifests and runtime profiles are active. |
| `raster-overlay` | NASA GIBS, RainViewer, TomTom traffic, ESA, and EEA manifests are classified. GIBS and RainViewer provider descriptors are implemented. |
| `vector-overlay` | OpenAQ, Census TIGERweb, USGS, NOAA, FEMA, NASA FIRMS, Open Charge Map, NREL AFDC, and ArcGIS REST descriptors are implemented for normalized API contracts. Open Charge Map and NREL AFDC also support live JSON fetch, normalization, and stale-cache fallback. |
| `search-index` | Overpass, Geoapify, and OpenTripMap sources are classified. Overpass has a concrete provider adapter; OpenTripMap supports live JSON fetch, normalization, and stale-cache fallback when credentials are configured. |
| `camera-network` | Windy Webcams manifest, provider shell, credential status, API contract, and client types are implemented. |
| `dataset-ingestion` | GTFS Static, OurAirports, Natural Earth, Census boundaries, ACS joins, Eurostat NUTS, Overture Maps, OpenAddresses, and local parcel template manifests are classified. The ingestion service executes CSV/GeoJSON normalization and records partial status for heavy formats that need optional GIS dependencies. |
| `analysis-tool` | Open-Meteo and PVGIS provider adapters are implemented for point or sampled analysis payloads. |
| `metadata-only` | Statistical or restricted sources are classified and not exposed as normal map toggles. |

## Official References

- Windy Webcams API: https://api.windy.com/webcams/docs
- GTFS Realtime: https://developers.google.com/transit/gtfs-realtime
- NASA Open APIs: https://api.nasa.gov/
- NASA GIBS: https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api
- Open-Meteo: https://open-meteo.com/en/docs
- OpenAQ: https://docs.openaq.org/using-the-api/api-key
- Overpass: https://wiki.openstreetmap.org/wiki/Overpass_API
- TomTom: https://docs.tomtom.com/platform/documentation/my-tomtom/how-to-get-a-tomtom-api-key/
- Geoapify: https://apidocs.geoapify.com/
- GTFS Schedule: https://gtfs.org/schedule/reference/
- USGS Earthquake GeoJSON: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- USGS Water Services: https://waterservices.usgs.gov/
- NOAA/NWS API: https://www.weather.gov/documentation/services-web-api
- NOAA CO-OPS API: https://api.tidesandcurrents.noaa.gov/api/prod/
- FEMA NFHL: https://hazards.fema.gov/femaportal/wps/portal/NFHLWMS
- NASA FIRMS API: https://firms.modaps.eosdis.nasa.gov/api/
- OpenTripMap: https://opentripmap.io/docs
- Open Charge Map: https://openchargemap.org/site/develop/api
- NREL AFDC: https://developer.nrel.gov/docs/transportation/alt-fuel-stations-v1/
- OurAirports: https://ourairports.com/data/
- Transitland: https://www.transit.land/documentation/datastore/api-endpoints.html
- Natural Earth: https://www.naturalearthdata.com/downloads/
- Census cartographic boundaries: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html
- Census ACS: https://www.census.gov/data/developers/data-sets/acs-5year.html
- Eurostat GISCO NUTS: https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/territorial-units-statistics
- Overture Maps: https://docs.overturemaps.org/
- OpenAddresses: https://batch.openaddresses.io/data

## Current Provider Framework

Provider adapters live under `app/server/services/geospatial/providers`.

Implemented adapters:

- `arcgis_rest.py`
- `census.py`
- `geoapify.py`
- `gtfs_realtime.py`
- `gtfs_static.py`
- `fema.py`
- `nasa_gibs.py`
- `nasa_firms.py`
- `noaa.py`
- `nrel.py`
- `openaq.py`
- `openchargemap.py`
- `openmeteo.py`
- `opentripmap.py`
- `overpass.py`
- `ourairports.py`
- `pvgis.py`
- `rainviewer.py`
- `tomtom.py`
- `usgs.py`
- `windy_webcams.py`

Adapters return normalized `ProviderResponse` objects with payload, attribution, warnings, stale state, and provider ID. Network-dependent behavior is tested through mocked services.

Downloaded datasets are represented as manifests and processed by `app/server/services/geospatial/ingestion.py`. The default runtime can normalize CSV point data and GeoJSON feature collections; heavy formats remain optional to keep the web stack lightweight.
