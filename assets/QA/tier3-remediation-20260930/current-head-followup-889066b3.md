# Current-head raster and isolated follow-up

Date: 2026-09-30
Source boundary: `develop@889066b3` (`fix: enforce raster visibility across
render modes`). The working tree was clean before the documentation and QA
updates recorded after this source commit.

## Confirmed remediation

`AgentRunRepository.acknowledge_render` now treats every supported raster mode
(`raster-tile`, `tile`, `xyz`, `wms`, and `wmts`) as requiring authoritative
`result_visible: true` evidence for a non-empty candidate. A declared
`valid_empty` result remains the only empty-raster exception. The regression
matrix is in `app/tests/unit/services/test_render_completion.py`.

## Current-head quality evidence

| Check | Result |
| --- | --- |
| Focused render-contract unit suite | `26 passed` |
| Full backend unit suite | `1034 passed`, 2 dependency deprecation warnings |
| Full Ruff | `All checks passed` (three access-denied warnings from protected historical QA paths) |
| Pyright strict | `0 errors, 0 warnings, 0 informations` |
| Angular production build | Pass with `npm --prefix app/client run build -- --verbose --progress=false` |
| Full Karma | `264/264 SUCCESS` |
| Strict production layer auditor | `manifest_count=86`, `error_count=0`, `warning_count=0` |
| Git diff check | Pass |

The first plain production-build invocation exited without diagnostics; the
verbose retry above completed successfully. No source fallback or dependency
change was made.

## Isolated RainViewer observations

Disposable runtime: `runtimes/cache/test-runtime/codex-rainviewer-20260930`.
The normal runtime database and settings were not copied or changed.

- `GET /api/geospatial/capabilities` exposed the RainViewer capability as
  available, map-supported, `raster-tile`, maximum zoom 7, and attributed
  `© RainViewer`.
- Naples-bounded provider execution returned `status=ok`, `frameCount=13`,
  `maxZoom=7`, a frame time window, and `stale=false`.
- The same-origin proxy returned `200 image/png`, `content-length=20642` for
  `/api/geospatial/tiles/rainviewer_precipitation_radar/4/3/6.png`.
- The Codex in-app browser displayed the real colored 256x256 radar tile. The
  `/geodata` catalog displayed `86 entries`, `Ready`, 18 providers, and 6
  basemaps.

The exact required agent lane was not executable in this disposable runtime.
The settings read had no selected model or credential; the supported settings
update failed closed with `OpenCode Go credentials are not configured`, and
the structured probe reported that the selected provider ID was not canonical.
No credential was copied, entered, or transmitted. No agent run or accepted
`map.render_ack` is claimed, so `T3-09` remains `PARTIAL`.

## Boundary

This report proves the current-head render-contract regression and bounded
RainViewer provider/proxy/browser behavior. It does not promote T3-07 or T3-09
to `PASS`: FEMA/ESA transport and the exact-lane agent MapLibre acknowledgement
remain unproven.
