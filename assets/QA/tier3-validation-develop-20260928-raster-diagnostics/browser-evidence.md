# Browser evidence — raster request diagnostics

- Date: 2026-09-28
- Source: `develop@047673c6712512c93cc828895536727255fe2cca`
- Provider/model: `opencode-go / deepseek-v4.1-flash`
- Structured probe: PASS (`HTTP 200`, `parse_status=complete`)

The in-app Browser first reproduced the existing FEMA failure and displayed the
last-known-good empty workspace rather than a false ready map. The Playwright
rerun used a fresh chat for each scenario and captured browser request failures.

## FEMA NFHL — New Orleans

- 15 ArcGIS export requests were issued.
- No response event or HTTP status was observed.
- One request failed with `net::ERR_CONNECTION_RESET`; the remaining 14 were
  `net::ERR_ABORTED` cancellation events after the source failure.
- The UI reported `source_present: false`, `layer_present: false`, and no
  verified map; no MapLibre map/canvas was present in the final page.

## ESA WorldCover — Rome

- 12 Terrascope WMTS requests were issued.
- No response event or HTTP status was observed.
- All 12 failed with `net::ERR_HTTP2_PROTOCOL_ERROR`.
- The UI reported that the WorldCover source could not load; no MapLibre
  map/canvas, raster pixels, or accepted `map.render_ack` was present.

The request URLs are retained in the scenario JSON with credential-like query
parameters redacted. No authorization headers or request bodies were captured.
