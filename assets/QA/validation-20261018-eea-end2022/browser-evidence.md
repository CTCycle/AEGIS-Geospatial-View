# Browser evidence — 2026-10-18

Lane: `opencode-go / deepseek-v4.1-flash`, exact selection, no fallback. The browser used the isolated local AEGIS runtime.

## EEA END-2022, Milan

- The app selected capability `eea_noise_end2022`; spatial scope resolved to Milan, Italy and was marked satisfied.
- The visible overlay was `EEA END-2022 Noise Exposure`, with attribution `© European Environment Agency — END-2022; research/non-profit use only; nationally restricted contours excluded`.
- The descriptor used the same-origin template `/api/geospatial/tiles/eea_noise_end2022/{z}/{x}/{y}.png`, WMS 1.1.1, layers `0,17,34,51`, and XML exceptions `application/vnd.ogc.se_xml`.
- The backend accepted the browser `map.render_ack`; persisted `render_observed` sequence 53 reported `status=ready`, required sources and layers loaded, valid viewport, source/layer present and visible, intersecting tile, and 1,584 non-transparent raster pixels. The run resumed and completed. The realtime acknowledgement frame itself was not separately captured.
- The map note identified the END-2022 reporting vintage and 2025 service update.
- The UI visibly showed the raster over the Milan basemap with the EEA attribution.

## Coverage guardrail and layer lifecycle

- A Chicago request was rejected because the EEA source covers Europe and the candidate tile did not intersect the viewport (`raster_tile_outside_viewport`). The last-known-good map remained unchanged.
- GBIF species observations were added to the Milan map while the EEA layer remained visible; both attributions were shown.
- The EEA layer was then removed while GBIF remained visible. The UI verified the final one-layer state.
- A separate Overpass pharmacy request failed because Overpass was temporarily unavailable; GBIF was used for the successful add/remove lifecycle case.

## ESA and FEMA rechecks

- ESA WorldCover in Rome passed: source and layer loaded, visible raster pixels were reported as 64,744, and `© ESA WorldCover / Terrascope` attribution was visible. The data vintage is 2021.
- FEMA NFHL in New Orleans returned renderable provider data and spatial scope, but the browser render failed at MapLibre: source absent, required sources not loaded. The response identified FEMA's ArcGIS Online relay as unavailable. No FEMA pixels were presented.

## Network-capture limitation

The direct browser request count for `noise.discomap.eea.europa.eu` is **unobserved**. The in-app Browser controls used for the visible run do not expose request events. The repository Playwright capture test did not reach its test body: setup remained at the Chromium/browser fixture after `browser_type_launch_args`, so it was stopped without recording a test result or request count. The source descriptor is same-origin and the rendered source/pixel evidence is positive, but this does not prove that the page made zero direct EEA requests. Accordingly `T3-15` and `RASTER-LIVE` stay `PARTIAL`.
