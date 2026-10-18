# EEA END-2022 raster validation

Date: 2026-10-18
Branch: `develop`
Starting HEAD: `1e1fac3652c7280a6ffadff88fb28c50cb40d26b`
Validated implementation commit: `c09763096d1f4aa1b9a31e37a88e4c16b0b9716c`
Runtime: isolated local backend on port `5079`; exact `opencode-go / deepseek-v4.1-flash` lane; no fallback.

## Result

The EEA END-2022 service renders successfully in Milan through the new same-origin AEGIS tile descriptor. The browser showed the noise contour overlay, EEA attribution and the END-2022/service-2025 freshness note. The backend accepted the browser's `map.render_ack`: it emitted the matching `render_observed=ready` event with all required sources/layers loaded and 1,584 non-transparent pixels in the intersecting tile, then resumed and completed the run. The websocket acknowledgement frame was not separately captured; acceptance is evidenced by the backend's persisted ready observation and run continuation. The EEA-plus-GBIF add/remove workflow passed, and an out-of-coverage Chicago request was rejected while preserving the last-known-good map.

`T3-15` remains `PARTIAL`: its live render, spatial guardrail and mixed-layer lifecycle passed, but zero direct browser requests to EEA was not measured. The in-app browser exposes no request listener, and the Playwright capture runner stalled while setting up Chromium before the test body created artifacts. The map source descriptor recorded by the browser is same-origin (`/api/geospatial/tiles/eea_noise_end2022/{z}/{x}/{y}.png`), while the server-side proxy uses the official EEA service, but that does not substitute for the required browser request count.

`RASTER-LIVE` remains `PARTIAL`. ESA WorldCover passed its current browser check. FEMA data retrieval succeeded, but the current browser run failed at MapLibre source loading: the source was absent and FEMA's official ArcGIS relay was unavailable. The previous FEMA pass remains historical evidence; this current failure supersedes it for the current status. EEA rendered, but its direct-request count is still unobserved.

`T3-07` is now `PARTIAL` for the same current FEMA relay failure; ESA still passes. `GEO-FOCUS-16` and `MATRIX-22` remain `PARTIAL` for Census timeouts/manual-toggle reachability, disabled elevation, imagery temporal/render-scope failures and wider matrix gaps. `ROUTE-LIVE` remains `PARTIAL`; F-13/F-19 and other route rows remain separate. `T3-18` remains `PASS`; the current F-21–F-23 follow-up remains `PASS` and supersedes earlier failures in older reports.

## Checks

- Strict production manifest audit: passed, zero warnings.
- Focused EEA, descriptor and runtime-profile tests: 87 passed.
- Full backend unit suite: 1,113 passed.
- Ruff: passed.
- Strict Pyright: passed with zero errors, warnings or information messages.
- Exact-lane browser: EEA Milan render and GBIF add/remove passed; Chicago coverage guardrail rejected; ESA Rome rendered with 64,744 non-transparent pixels; FEMA New Orleans retrieval succeeded but MapLibre source loading failed at the relay boundary.
- Automated browser request capture: not completed. The Playwright test remained in `browser_type_launch_args` / Chromium fixture setup and was interrupted after it produced no test artifacts; no browser request-count claim is made.
- The helper runtime launcher failed to start its backend. A manually launched isolated backend was then bootstrapped in-process to the exact provider/model lane; the sanitized records are in `runtime/`.
- Hosted CI run [39161534103](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/39161534103) completed successfully for pushed `develop@c09763096d1f4aa1b9a31e37a88e4c16b0b9716c`: all four standard jobs passed. This hosted result is separate from the local exact-lane browser evidence.

## Official source metadata

- [EEA END-2022 dataset record](https://sdi.eea.europa.eu/catalogue/eea-statistical-data/api/records/853e72e4-4642-47d1-8556-2cc231bd43e0?language=eng): the record identifies the 2022 Environmental Noise Directive mapping round, a 2021 temporal extent, submissions through 2024-11-18, and publication in March 2026.
- [EEA Noise_exposure_2025 service](https://noise.discomap.eea.europa.eu/arcgis/rest/services/noiseStoryMap/Noise_exposure_2025/MapServer): the service metadata reports a 2025 data update and exposes the Industry, Road Transport, Rail Transport, and Aviation groups used by the WMS.

## Source limitation

The EEA catalogue record limits this dataset to research/non-profit use and excludes nationally restricted contours. This validation is technical; it does not establish commercial-use clearance or national contour completeness.

## Cleanup

The isolated backend was stopped after the browser run. Port 5079 was verified
free, and the task-owned data directory
`runtimes/cache/test-runtime/eea-end2022-manual` was removed after resolving
and checking that its path was within `runtimes/cache/test-runtime`.

## Evidence

- [Browser evidence summary](browser-evidence.md)
- [Sanitized browser evidence](browser-evidence.json)
- [Exact-lane probe summary](runtime/exact-lane-probe.json)
- [Manual runtime summary](runtime/live-runtime.json)
- [Runtime-helper launch attempt](runtime/launcher-attempt.json)
- [Manifest audit](manifest-audit.log)
- [Focused tests](focused-tests.log)
- [Full backend unit suite](backend-unit-full.log)
- [Ruff](ruff.log)
- [Strict Pyright](pyright.log)
- [Hosted CI result](hosted-ci.json)
