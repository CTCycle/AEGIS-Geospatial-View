# Provider Framework

Last updated: 2026-06-19

## Provider Adapter Location

Provider adapters live under `app/server/services/geospatial/providers`.

## Implemented Adapters

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
- Provider adapters must not return credentials or raw capability XML to frontend API responses.

## Dataset Processing Boundary

Downloaded datasets are processed by `app/server/services/geospatial/ingestion.py`. The default runtime handles CSV point data and GeoJSON feature collections. Heavy GIS formats remain optional.
