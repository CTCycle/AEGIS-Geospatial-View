# AEGIS hazard and hydrology E2E rerun

Run date: 2026-09-20.

This is the follow-up live-browser rerun for the eight-scenario hazard and
hydrology matrix. It was run from source commit `84c210f6` on branch
`loop-dev` with the exact `opencode-go / deepseek-v4.1-flash` lane. No model or
provider fallback was used.

## Decision

**PARTIAL.** The FEMA adapter now returns the current ArcGIS export descriptor
and the agent retrieves a raster result, but the public FEMA raster source still
fails the browser-side MapLibre load/acknowledgement. GEO-HYD-05 and
GEO-HYD-06 therefore remain blocked. The current Zurich rerun is inconclusive
because the agent stopped after repeated invalid tool calls; the earlier
2026-09-19 coverage-guardrail PASS is retained as historical evidence only.

## Repository and runtime

- Repository: `CTCycle/AEGIS-Geospatial-View`
- Branch: `loop-dev`
- Source commit tested: `84c210f6` (`fix: use current FEMA NFHL ArcGIS export endpoint`)
- Provider/model lane: `opencode-go / deepseek-v4.1-flash`
- Backend/frontend: `127.0.0.1:7059` / `127.0.0.1:4512`
- The UI displayed the exact lane; after the first successful USGS request it
  displayed `Agent model: Verified`.
- Services were stopped after the browser run. Ports `7059`, `4512`, and `9876`
  were verified free.
- Browser screenshots were observed inline during the live run. The available
  browser-control surface did not expose filesystem screenshot export, so no
  invented screenshot filenames are recorded here.

## Validation and quality checks

- Post-fix focused regression set: `54 passed in 1.42s`.
- Ruff over the changed Python files: passed with `All checks passed!`.
- `git diff --check`: passed; only normal LF-to-CRLF working-copy warnings were
  emitted.
- The previously recorded focused checkpoint suite remains `120 passed`; this
  rerun used the narrower post-fix boundary set above.
- The ACL-protected untracked `app/tests/cache/` pytest tree was preserved after
  cleanup was refused by permissions.

## Scenario matrix

| ID | Capability | Prompt / action | Final status | Browser evidence |
|---|---|---|---|---|
| GEO-HYD-01 | `fema_nfhl_flood_zones` | FEMA flood zones around New Orleans | **PARTIAL** | FEMA data retrieval returned a raster result; the FEMA layer and attribution attached, but two MapLibre attempts ended in `render_failed` because the raster source could not load. No verified FEMA map was committed. |
| GEO-HYD-02 | `usgs_water_gauges` | Active USGS gauges around Austin | **PASS** | MapLibre showed the USGS clustered-point layer and attribution; 48 features were retrieved and 13 gauge points were visible in the current viewport. |
| GEO-HYD-03 | `census_tigerweb_hydrography` | Rivers and water features around Seattle | **PASS** | Census hydrography rendered as the visible line/polygon layer with attribution; 13 features were retrieved and 15 were rendered. |
| GEO-HYD-04 | `noaa_weather_alerts` | Current NOAA alerts around Houston | **PASS** | NOAA returned valid-empty with zero alerts; a verified Houston location-only map was shown without fabricating an overlay. |
| GEO-HYD-05 | FEMA + USGS composition | Add nearby active USGS gauges after FEMA New Orleans | **BLOCKED** | The second turn produced a verified USGS-only map (15 retrieved, 6 visible) and explicitly reported that the earlier FEMA overlay was not rendered. Both sources were not simultaneously visible. |
| GEO-HYD-06 | Selective removal | Remove gauges but keep FEMA | **BLOCKED** | The UI confirmed the gauges were removed, but the FEMA source failed again; the final state was basemap-only and no FEMA layer was verified. |
| GEO-HYD-07 | FEMA coverage guardrail | FEMA flood zones around Zurich | **RERUN INCONCLUSIVE** | Two fresh attempts ended with `The agent stopped after repeated invalid tool calls`; no provider execution or coverage-rejection acknowledgement was accepted from this rerun. The prior checkpoint PASS remains historical, not current rerun proof. |
| GEO-HYD-08 | `census_tigerweb_hydrography` | Move Seattle hydrography to Portland and keep only that layer | **PASS** | Portland was rendered with only the Census hydrography layer; 543 features were retrieved and 514 rendered, with the layer visible and attributed. |

## FEMA evidence

Exact prompt: `Show FEMA flood zones around New Orleans, Louisiana.` The
execution details showed successful location resolution, FEMA capability
description, and `execute_geospatial_capability` returning a raster result from
provider `fema`. The map candidate attached `FEMA Flood Zones` and Federal
Emergency Management Agency attribution. The final UI then reported:

> Render verification failed twice. Both attempts (default basemap, then
> imagery basemap with reduced overlay opacity) reported `render_failed` at the
> MapLibre stage: the FEMA flood-zone raster source could not be loaded.

This is a live-provider/render limitation after the descriptor and URL-template
fix, not a successful FEMA render. No third-party mirror, WMS fallback, or
renderer weakening was introduced.

## Composition and removal evidence

The mixed conversation first attempted FEMA New Orleans and then received
`Add nearby active USGS water gauges.` The final assistant text explicitly said
the USGS map was verified and that the current map showed only USGS gauges
because FEMA had failed to render. This does not satisfy GEO-HYD-05.

The follow-up `Remove the water gauges but keep the FEMA flood zones.` produced
the explicit result that the water gauges were removed, while FEMA again failed
at MapLibre and the map was left with no data overlay. This does not satisfy
GEO-HYD-06, although the removal side effect itself was visibly confirmed.

## Remaining boundary

The next meaningful gate is upstream/provider investigation of why the current
FEMA ArcGIS export raster source cannot load in the browser renderer. Until a
live FEMA source/layer/render acknowledgement is observed, keep GEO-HYD-01
PARTIAL and GEO-HYD-05/GEO-HYD-06 BLOCKED. Do not promote the overall matrix to
PASS from the successful USGS, Census, NOAA, or historical Zurich evidence.
