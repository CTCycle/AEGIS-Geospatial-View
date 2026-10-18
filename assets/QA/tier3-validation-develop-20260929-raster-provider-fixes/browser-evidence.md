# T3 raster browser evidence — 2026-09-29

Lane: `opencode-go / deepseek-v4.1-flash`, branch `develop`, local backend `7059`, local frontend `4512`. The in-app Browser was used for UI inspection, and the instrumented Playwright Chromium harness captured network, MapLibre, pixel, attribution, and acknowledgement evidence.

## T3-08 GIBS

The complete 12-case matrix was exercised. The final per-case evidence is `12/12`:

- every case selected its advertised AEGIS capability and provider-native GIBS layer;
- every target request stayed on `/api/geospatial/tiles/...` with zero direct browser requests to NASA GIBS;
- every case returned `200 image/png`, created a MapLibre source and raster layer, showed non-empty raster pixels, retained NASA attribution, and emitted accepted `render_observed`;
- temporal values were captured where the provider advertised them; the full case table is in [gibs-trace-summaries.json](gibs-trace-summaries.json).

The repaired fire chain is explicit:

`MODIS_Combined_Thermal_Anomalies_Fire` → `MODIS_Combined_Thermal_Anomalies_All` → AEGIS raster proxy → `200 image/png` → visible MapLibre raster → `render_observed`.

The first complete matrix attempt encountered one transient exact-lane discovery-tool failure for the land/water-mask prompt before any target request. That same case was rerun with the unchanged provider/model and met all acceptance criteria; no provider or model substitution was used.

## T3-07 ESA and FEMA

ESA WorldCover is `PASS`: the agent selected `esa_worldcover`; the browser used the AEGIS proxy; the proxy reached `https://titiler.terrascope.be/wms` with layer `esa-worldcover-map-10m-2021-v2_map`, `EPSG:3857`, WMS `1.3.0`, `image/png`, and `TIME=2021-01-01`; 12 proxy responses were `200 image/png`; MapLibre source/layer and visible pixels were present; ESA/Terrascope attribution and `render_observed` were present; direct Terrascope browser requests were zero. See [ESA browser capture](screenshots/RASTER-LIVE-DIAGNOSTICS/esa_worldcover_rome.png).

FEMA remains `PARTIAL`: the existing ArcGIS export endpoint and bounded `bboxSR=3857`, `imageSR=3857`, `format=png32`, `transparent=true` construction were verified and left unchanged. Browser traffic stayed on the AEGIS proxy, but FEMA returned `transport_error` before a status/content-type response; no FEMA pixels, acknowledgement, composition, or selective-removal proof exists. See [FEMA browser capture](screenshots/RASTER-LIVE-DIAGNOSTICS/fema_new_orleans.png).

Therefore the combined gate remains `T3-07: PARTIAL` despite ESA passing.
