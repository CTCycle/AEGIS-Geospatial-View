# Provider Framework

Last updated: 2026-08-02

## Provider Adapter Location

Provider adapters live under `app/server/services/geospatial/providers`.

## Implemented Adapters

- `arcgis_rest.py`
- `census.py`
- `eea.py`
- `esa.py`
- `eurostat.py`
- `gtfs_realtime.py`
- `gtfs_static.py`
- `fema.py`
- `local_open_data.py`
- `mapillary.py`
- `mobility_database.py`
- `nasa_gibs.py`
- `nasa_firms.py`
- `natural_earth.py`
- `noaa.py`
- `nominatim.py`
- `openaddresses.py`
- `openaq.py`
- `openchargemap.py`
- `openmeteo.py`
- `opentripmap.py`
- `overpass.py`
- `overture.py`
- `ourairports.py`
- `pvgis.py`
- `rainviewer.py`
- `tomtom.py`
- `usgs.py`
- `windy_webcams.py`

MapLibre style basemap providers such as OpenFreeMap are rendering-only
providers. They do not require a backend adapter; their concrete fetch path is
the public style document consumed by the frontend renderer.

## Response Contract

Adapters return normalized `ProviderResponse` objects with:

- payload
- attribution
- warnings
- stale state
- provider ID

Adapters that support live layer discovery additionally expose:

- `list_layers(query, limit, refresh)`
- `describe_layer(layer_id, refresh)`

These methods return normalized provider layer descriptors. NASA GIBS parses WMS/WMTS XML capabilities and prefers WMTS render descriptors when a Web Mercator tile matrix set is available, falling back to WMS only when needed.

## Provider Expectations

- Feature providers expose `fetch_features(request)` or an equivalent registry path.
- Cache keys include safe request-shaping parameters such as provider, layer ID, bbox, zoom, time, category, variables, and credential-safe request parameters.
- Provider results include attribution and source-health metadata when available.
- 401, 403, 429, timeout, malformed, empty, and stale-cache states are surfaced as safe payloads without leaking credentials.
- Hazard providers include legends and freshness labels where applicable.
- Local open-data camera templates read configured JSON source URLs or files through `LOCAL_OPEN_DATA_SOURCES`.
- Mobility Database discovery reads a local CSV snapshot and refreshes it from the public catalog only when the snapshot is missing or explicitly requested; each feed's authentication and license metadata is preserved.
- Provider adapters must not return credentials or raw capability XML to frontend API responses.

## Dataset Processing Boundary

Downloaded datasets are processed by `app/server/services/geospatial/ingestion.py`. The default runtime handles CSV point data and GeoJSON feature collections. Heavy GIS formats remain optional.
