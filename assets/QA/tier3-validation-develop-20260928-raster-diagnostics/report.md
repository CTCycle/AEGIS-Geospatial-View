# Tier 3 raster request diagnostics

- Date: 2026-09-28
- Tested application source: `develop@047673c6712512c93cc828895536727255fe2cca`
- Provider/model: `opencode-go / deepseek-v4.1-flash`
- Runtime: isolated `runtimes/cache/test-runtime/tier3-raster-remediation-20260928`
- Browser path: Codex in-app Browser for visual confirmation, then Playwright for request-level events

## Result

The exact provider/model structured probe passed (`HTTP 200`, `parse_status=complete`).
The in-app Browser reproduced the existing FEMA failure before request-level
capture was added. The corrected Playwright diagnostic then started a fresh chat
for each scenario and recorded the actual public raster requests.

| Scenario | Requests | Responses | Browser failures | Visible map | Acceptance |
| --- | ---: | ---: | --- | --- | --- |
| FEMA NFHL, New Orleans | 15 | 0 | 1 `ERR_CONNECTION_RESET`; 14 `ERR_ABORTED` cancellations | No MapLibre map or canvas | No raster pixels or accepted `map.render_ack` |
| ESA WorldCover, Rome | 12 | 0 | 12 `ERR_HTTP2_PROTOCOL_ERROR` | No MapLibre map or canvas | No raster pixels or accepted `map.render_ack` |

FEMA requests used the expected ArcGIS export path and the expected Web
Mercator image parameters, including `bbox`, `bboxSR=3857`, `imageSR=3857`,
`size=256,256`, `format=png32`, `transparent=true`, and `f=image`.

ESA requests used the expected Terrascope WMTS path with
`layer=WORLDCOVER_2021_MAP`, `tilematrixset=EPSG:3857`,
`tilematrix=EPSG:3857:<zoom>`, and `format=image/png`.

There were no response events or HTTP statuses for either provider. The
captured browser failures occur before an image response reaches MapLibre, so
the evidence does not identify a repository-owned URL or renderer defect. No
production renderer, descriptor, provider, or `map.render_ack` contract change
was made.

## Evidence

- [FEMA request capture](http/RASTER-LIVE-DIAGNOSTICS/fema_new_orleans.json)
- [ESA request capture](http/RASTER-LIVE-DIAGNOSTICS/esa_worldcover_rome.json)
- [FEMA visual result](screenshots/RASTER-LIVE-DIAGNOSTICS/fema_new_orleans.png)
- [ESA visual result](screenshots/RASTER-LIVE-DIAGNOSTICS/esa_worldcover_rome.png)
- [Diagnostic test report](reports/RASTER-LIVE-DIAGNOSTICS.json)
- [Quality checks](quality-checks.log)
- [Cleanup checks](cleanup-checks.md)
- [Reusable diagnostic test](../../../app/tests/e2e/test_live_raster_diagnostics.py)

## Gate disposition

T3-07 remains PARTIAL. FEMA-dependent `GEO-HYD-05` and `GEO-HYD-06` remain
BLOCKED, while `LIVE-HYD` and `MATRIX-22` remain PARTIAL. The USGS control and
empty-overlay acknowledgement do not establish FEMA retention. A future retry
needs a browser/network environment that returns an image response or exposes
the upstream HTTP status; only a confirmed repository-owned defect should
trigger a renderer or descriptor fix.
