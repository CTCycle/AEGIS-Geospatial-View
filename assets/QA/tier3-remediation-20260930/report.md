# Tier 3 raster visibility remediation

Date: 2026-09-30
Source boundary: `develop@db3d650a931d3e22367bb4d11992b8c1c71e6b84` plus the
uncommitted working tree listed in the final repository status.

## Outcome

The P0 raster visibility contract is implemented and passes controlled client,
backend, and browser-proxy checks. Raster evidence is fail-closed: a missing
source/layer, unavailable tile, non-image response, decode/canvas failure, or
unproven provider state remains `result_visible: null` rather than becoming a
success. Valid-empty raster results may complete with zero non-transparent
pixels.

The end-to-end MapLibre agent gate remains `PARTIAL`. The isolated browser
runtime has no selected agent model, so the attempted chat route remained at
`Needs attention` and did not produce an accepted `map.render_ack`. FEMA,
ESA, NOAA, and EEA public tile probes also returned backend `502` responses in
this environment. Those upstream transport failures are retained as provider
limitations; no proxy expansion was made speculatively.

## Implementation

- `app/client/src/app/components/raster-visibility.ts` builds a bounded probe
  from the active viewport, overlay bounds, zoom, center, and temporal tile
  template; checks source/layer/visibility/opacity; fetches same-origin image
  data; decodes it; and counts alpha-bearing pixels.
- `map-preview.component.ts` records the raster observation in the render
  acknowledgement fields, including source-loaded state, viewport
  intersection, zoom support, tile coordinates, and non-transparent pixel
  count. Unknown observations are preserved as unknown.
- `realtime.py` validates the bounded raster acknowledgement fields.
- `agent_runs.py` requires visible raster proof for non-empty raster results,
  while allowing a declared `valid_empty` raster to complete without pixels.

## Controlled validation

| Check | Result |
| --- | --- |
| Raster visibility spec | 9/9 pass: opaque, transparent, non-image, hidden, opacity zero, outside viewport, missing source/layer, unsupported zoom, temporal selection, and failure/recovery behavior |
| Map preview component spec | 33/33 pass |
| Full Angular/Karma suite | 264/264 pass |
| Geospatial browser smoke spec | 6/6 pass |
| Frontend state tests | 19/19 pass |
| Angular production build | pass |
| Backend render-completion contract tests | 18 pass |
| Backend unit suite with explicit local service URLs | 1,026 pass; 2 dependency warnings |
| Repository Playwright E2E slice with explicit local service URLs | 52 pass, 25 skipped, 3 failures |
| Targeted Ruff | pass |
| Strict manifest auditor | pass; 86 manifests, 0 errors, 0 warnings |

The backend contract suite also covers repeated acknowledgements, stale or
mismatched revisions, raster visibility requirements, and the valid-empty
exception.

The three E2E failures are separately bounded: two chat assertions cannot
complete because the isolated runtime has no selected agent model, and one
overlay-refresh assertion reproduces in isolation outside the raster files
changed here. No unrelated overlay-state rewrite was made.

## Live/browser observations

- Full-size Chrome rendered the `/geodata` catalog with `86 entries`, `Ready`,
  18 providers, 6 basemaps, and the EEA/ESA/GIBS/NOAA/RainViewer records.
- The same-origin RainViewer tile route rendered a visible PNG in Chrome.
  The backend proxy returned `200 image/png` for
  `rainviewer_precipitation_radar` and GIBS `IMERG_Precipitation_Rate`.
- Bounded backend proxy checks returned `502` for `noaa_radar`,
  `eea_noise_2019`, `fema_nfhl_flood_zones`, and `esa_worldcover`; no image
  content or MapLibre pixels were claimed for those providers.
- The strict live provider validator exited non-zero with 11 failures. Most
  public failures were socket restrictions (`WinError 10013`) in its direct
  urllib lane; this is recorded as an environment/provider boundary, not as
  a passing application result.

## Status hand-off

- `T3-07`: remains `PARTIAL`; FEMA/ESA transport and dependent
  composition/removal are unproven.
- `T3-08`: prior GIBS browser evidence remains `PASS`; this remediation does
  not change that status.
- `T3-09`: remains `PARTIAL`; a functional RainViewer proxy/pixel check passed,
  but the required exact-model disposable agent run was unavailable.
- `maps.raster-overlays` and dependent state-preservation remain `PARTIAL`
  until a real MapLibre session emits source/layer/pixel evidence and an
  accepted `map.render_ack` for the remaining provider/composition paths.

No credentials were added or transmitted. Started local services and browser
tabs are cleaned up after this validation turn.
