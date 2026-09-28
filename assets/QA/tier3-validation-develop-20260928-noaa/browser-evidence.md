# T3-04 NOAA browser evidence

Date: 2026-09-28

Source boundary: `develop@acf01a580166fc685eb5bde52f4e4cca2482d4a3`

Lane: exact `opencode-go / deepseek-v4.1-flash`; no fallback or provider switch
was used. The local runtime used the relocated canonical data root
`app/resources`, with backend `7059` and frontend `4512`.

## Request and rendered result

The Codex in-app Browser submitted:

> Show me current NOAA weather alerts around Houston, Texas.

The visible response resolved `Houston, Harris County, Texas, United States`
and reported one active `Air Quality Alert` from the current NOAA/NWS snapshot.
The map was visibly centered on the Houston area and displayed the
`NOAA Weather Alerts` layer as `geojson`. The layer panel showed `1 of 1
visible`; the map showed the alert polygons, the `NOAA National Weather
Service` attribution was visible, and the MapLibre/OpenStreetMap attribution
was visible.

The rendered response reported 22 alert polygons across the wider region.
The provider response itself contained one normalized alert feature whose
usable `GeometryCollection` was assembled from official affected forecast-zone
boundaries because the alert product's own `geometry` was null.

## Tool trace

All four calls completed successfully:

1. `resolve_geospatial_location` — resolved Houston.
2. `describe_geospatial_capability` — described `noaa_weather_alerts`.
3. `execute_geospatial_capability` — returned one feature from provider
   `noaa`.
4. `apply_map_plan` — accepted the map candidate and waited for render
   acknowledgement.

The completed trace recorded `render_observed`, resumed finalization, and
completed the run. The UI status changed to `Agent model Verified`.

The screenshot was captured inline from the Codex in-app Browser during this
validation. That browser surface did not provide a local binary export, so no
unverifiable screenshot path is claimed here.

## Direct live provider check

A fresh `NOAAProvider` instance, with an empty in-memory geospatial cache,
returned:

```json
{
  "result_status": "ok",
  "partial": false,
  "feature_count": 1,
  "geometry_types": ["GeometryCollection"],
  "geometry_sources": ["affected_zones"],
  "warnings": [],
  "attribution": ["NOAA National Weather Service"]
}
```

The implementation resolves only canonical HTTPS NWS forecast-zone URLs,
bounds concurrent zone requests, caches successful zone geometries, preserves
the alert as partial/data-only when a zone lookup fails, and never converts an
unrenderable result into a renderer success. The official NOAA alert and API
service boundaries are documented at
https://www.weather.gov/documentation/services-web-alerts and
https://www.weather.gov/documentation/services-web-api.
