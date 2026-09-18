# AEGIS maps and first geospatial-overlay validation

Date: 2026-09-18
Scope: focused local E2E validation of startup, map rendering, basemaps, viewport/state management, first-slice overlays, layer lifecycle, failure recovery, and agent-to-map integration.

## Environment

- Branch: `develop`.
- Launcher: `.\start_on_windows.ps1 -Action Launch`.
- Backend: `server.app:app`, health endpoint on `http://127.0.0.1:7059`.
- Frontend: local preview on `http://127.0.0.1:4512`.
- Browser: Chrome via the in-app computer-use browser controls.
- Final application state: clean Vancouver location view, OpenStreetMap, no overlays, restored after browser reload.

## Coverage

Basemaps exercised: OpenStreetMap, OpenFreeMap Liberty, and OpenFreeMap Positron. Switching was repeated in both clean and overlay-active states.

Overlay/provider slice:

- USGS Earthquakes: current GeoJSON point feed; successful add, visibility, removal, re-addition, navigation, and render verification.
- Open-Meteo Weather Forecast: successful environmental fallback point layer; coexisted with USGS during the final pass.
- NASA GIBS VIIRS/MODIS imagery and IMERG precipitation: discovery/availability paths exercised; the local run reported temporary provider unavailability or no enabled execution capability.
- ESA WorldCover and RainViewer: discovery paths exercised; WorldCover returned a WMTS descriptor with unknown map eligibility, while the weather raster path was unavailable on the active route. No new provider was added.

Locations and navigation included Rome, Japan, Zurich, Iceland, Vancouver, northern Italy/Milan, and repeated distant-area movement. Geodata catalog UI was also inspected: 86 ready entries, 18 providers, 6 map types, and 48 layers were visible.

## Validation ledger

| Area | Scenario | Result | Issue | Fix | Retest |
| --- | --- | --- | --- | --- | --- |
| Startup/map | Clean launcher, initial map, resize, return from Geodata/Search | PASS | None in final run | — | Fresh launch and reload both rendered a single active map |
| Navigation | Wheel/control zoom, 10+ repeated zoom/pan actions, combined movement, distant locations | PASS | None in final run | — | Overlay state and render verification remained coherent |
| Basemap | OSM → Liberty → Positron → OSM, including active overlays | PASS | None in final run | — | Center/zoom context, layers, attribution, and rendered map remained stable |
| Map lifecycle | DOM map/canvas/control duplication check | PASS | None | — | One `.maplibregl-canvas` and one `.maplibregl-map` after reload |
| USGS Earthquakes | Add around Japan; render 4, display 2 clustered; hide/show; remove; re-add | PASS | Several routing/lifecycle defects found and fixed | See remediation chain below | Exact browser repetitions succeeded; final `map.render_ack`-equivalent UI said render verified |
| Weather companion | Add rainfall intensity; coexist with USGS; visibility toggle; remove via follow-up route | PASS | Local environmental fallback is point data, not raster | Existing fallback retained | Two visible layers, then clean removal/re-add/navigation verified |
| Raster imagery | NASA/Esri satellite request over Rome/Milan | ATTENTION | Providers were unavailable or no capability matched; no raster was rendered | No speculative provider change | UI retained the last-known-good map and the next valid request recovered after routing fixes |
| Land cover | Zurich/ESA WorldCover path | ATTENTION | WMTS descriptor had unknown map eligibility; alternate MODIS path was unavailable | No speculative provider change | No ghost layer or map corruption; state stayed unchanged |
| Failure recovery | Unsupported satellite request followed by valid USGS request in the same conversation | PASS | Router rejected valid `activity` term after failed request | Added routing-context token and test | Same conversation recovered to 4 USGS events and a verified map |
| Persistence | Browser reload after clean Vancouver state | PASS | None in final run | — | Vancouver, OSM, no overlays, and verified render state restored |
| Console/runtime | Final browser flows | PASS | No browser `warn`/`error` entries in final tab | — | Empty diagnostics after overlay, basemap, cleanup, reload flows |
| Multi-layer | Raster + vector requested; available local combination | ATTENTION | No raster provider rendered in this environment | Deferred provider availability | USGS + Open-Meteo point layers coexisted and remained synchronized |

## Issues found and remediated

### 1. Map overlay lifecycle and route state — `b5776e35`

- Issue: map evidence and overlay routes could omit the required map eligibility/bounds, local visibility changes could be overwritten by a later backend replay, and remove/re-add flows could retain stale layer IDs/evidence or expose incompatible tools.
- Root cause: the map plan, capability execution, context assembly, route/tool exposure, and frontend change-detection paths did not share one authoritative overlay/session lifecycle.
- Files changed: `app/server/prompts/agent.py`, `app/server/services/agent/agent_loop.py`, `app/server/services/agent/capability_execution.py`, `app/server/services/agent/capability_router.py`, `app/server/services/agent/context_assembler.py`, `app/server/services/agent/map_plan_service.py`, `app/server/services/agent/tool_executor.py`, `app/server/services/agent/tool_registry.py`, `app/server/services/geospatial/capability_registry.py`, `app/client/src/app/components/map-preview.component.ts`, plus the focused prompt/agent/capability/router/context/map-plan/tool/frontend tests in the same commit.
- Fix: preserved the last-known-good candidate until browser render evidence, made frontend visibility changes authoritative until the next committed revision, normalized target/layer IDs, and made map-state routes operate on the committed overlay collection.
- Exact retest: USGS Japan add → checkbox off/on → remove → re-add, including basemap switches and pan/zoom, succeeded in Chrome with a stable viewport and no console errors.
- Regression checks: weather visibility and opacity, two-layer coexistence, stale-layer cleanup, and final clean-map navigation all passed.

### 2. Catalog routing rejected a valid earthquake catalog query — `751eba14`

- Issue: discovery for `earthquakes seismic events earthquake catalog` returned `valid_empty` although the live capability catalog reported `usgs_earthquakes` enabled, healthy, and map-capable.
- Root cause: `catalog` was treated as an unmapped required routing term instead of query context.
- Files changed: `app/server/services/geospatial/capability_registry.py`; `app/tests/unit/services/geospatial/test_agentic_manifest_contract.py`.
- Fix: added `catalog` to `_ROUTING_CONTEXT_TOKENS` and added a shortlist regression assertion.
- Exact retest: after a normal launcher restart, the same browser request advanced past discovery to the next, separate initial-location failure; the later location fix then completed the full scenario.
- Regression checks: 12 focused manifest tests passed.

### 3. Initial `target_id` location resolution failed — `37abf997`

- Issue: `Show me earthquakes around Japan.` could call `resolve_geospatial_location` with `target_id="Japan"` and receive `unknown_location_target`.
- Root cause: the handler interpreted `target_id` only as an already stored state key; it did not treat an unresolved initial target as a resolver query.
- Files changed: `app/server/services/agent/tool_handlers/location.py`; `app/tests/unit/services/agent/test_location_tool_handler.py`.
- Fix: used unresolved `target_id` as the initial resolver query while preserving the existing early-return behavior for stored references.
- Exact retest: after launcher restart, Japan resolved, the USGS feed returned 4 features, 2 rendered in the viewport, and the UI reported render verification.
- Regression checks: fresh `Show me Rome.` rendered a clean location view; focused location tests passed 7/7.

### 4. Recovery routing rejected `activity` — `6892166e`

- Issue: after an unsupported satellite request, the next valid route queried `earthquake events seismic activity recent earthquakes`; discovery rejected USGS because `activity` was treated as a required subject term.
- Root cause: the routing-context vocabulary covered `event/events` and `recent` but not the neutral context word `activity`.
- Files changed: `app/server/services/geospatial/capability_registry.py`; `app/tests/unit/services/geospatial/test_agentic_manifest_contract.py`.
- Fix: added `activity` to `_ROUTING_CONTEXT_TOKENS` and asserted the exact route vocabulary selects `usgs_earthquakes`.
- Exact retest: in one browser conversation, Rome rendered, satellite failed coherently with no state mutation, then Japan recovered to 4 USGS events and a verified overlay.
- Regression checks: 12 focused manifest tests passed; final browser console diagnostics remained empty.

### 5. Pyright route-domain inference — `e06e04bc`

- Issue: repository Pyright reported `route_domains` as `set[CapabilityDomain] | set[Unknown]` at `tool_registry.py:215`.
- Root cause: the empty branch of the conditional set construction lacked an explicit element type.
- File changed: `app/server/services/agent/tool_registry.py`.
- Fix: added `set[CapabilityDomain]` to the local annotation; runtime behavior is unchanged.
- Retest: Pyright returned 0 errors; nearby agent/location tests passed 28/28.

### 6. Stale map-tool exposure test fixture — `2edd7e72`

- Issue: the full unit suite reported `test_exposure_is_phase_and_prerequisite_bound` because its fixture supplied only an old evidence reference for a fresh data route.
- Root cause: the lifecycle fix intentionally requires a successful data result with evidence for that route; the test encoded the old prerequisite contract.
- File changed: `app/tests/unit/services/agent/test_tool_exposure.py`.
- Fix: added a successful `execute_geospatial_capability` result carrying the fixture evidence reference.
- Exact retest: the failing test passed 1/1; nearby exposure/tool/location tests passed 30/30; the full unit suite then passed 853/853.

## Remaining issues

Release-blocking for this slice’s raster objective:

- No satellite, land-cover, or environmental raster was rendered in the local run. NASA GIBS/Esri imagery and IMERG/RainViewer paths were unavailable or returned no executable capability; ESA WorldCover did not provide a verified map-eligible descriptor. A broader raster/provider validation should not be considered complete from this run.

Non-blocking:

- Unsupported raster requests can still present `No supported capability matched the request after discovery`; the map remains usable and, after the routing fixes, a subsequent valid request recovers without an application restart.
- Automated suites emit dependency/framework warnings (FastAPI/httpx deprecation, Google GenAI union deprecation, Angular Karma builder deprecation, and expected test sanitization/404 fixture output). No final browser console warnings/errors were observed.

Deferred outside this slice:

- Full provider-catalog coverage, credentialed/restricted providers, complex agentic reasoning, and a true raster-plus-vector three-layer stack.
- Cleanup of older protected pytest-cache/temp directories that predated or outlived this run; exact removal attempts were denied by the workspace ACL, so no broad permission or ownership changes were made.

## Automated validation

Commands actually executed:

- `ruff check app/server app/tests`: launcher command unavailable (`ruff` not on PATH).
- `& '.\app\server\.venv\Scripts\ruff.exe' check app/server app/tests`: PASS; all checks passed, with access-denied warnings while scanning protected historical cache directories.
- `& '.\app\server\.venv\Scripts\pyright.exe' --project app/server/pyproject.toml`: initially failed at `tool_registry.py:215`; after `e06e04bc`, PASS with `0 errors, 0 warnings, 0 informations`.
- Focused routing manifest tests: `12 passed`.
- Focused location tests: `7 passed`.
- Nearby agent/location/exposure tests: `30 passed`.
- `& '.\app\server\.venv\Scripts\python.exe' -m pytest -c app/server/pyproject.toml app/tests/unit -q --basetemp=app/assets/QA/.pytest-tmp-full-unit-rerun`: PASS, `853 passed, 2 warnings in 20.42s`.
- `npm --prefix app/client run build`: PASS; Angular bundle generated successfully.
- `npm --prefix app/client test -- --watch=false --browsers=ChromeHeadlessNoGpu`: PASS, `TOTAL: 238 SUCCESS`; output included the Angular Karma deprecation notice, expected sanitization warning, and test-fixture 404.

## Final assessment

The core AEGIS map experience, basemap switching, viewport management, state synchronization, USGS vector lifecycle, available weather fallback lifecycle, and failure recovery are stable enough to proceed to a broader second validation slice. The first slice is not fully green for raster overlays or full heterogeneous provider coverage, and this result must not be interpreted as full AEGIS release readiness.
