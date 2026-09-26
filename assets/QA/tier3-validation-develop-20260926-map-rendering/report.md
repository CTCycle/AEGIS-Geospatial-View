# Tier 3 map-rendering validation follow-up

Run date: 2026-09-26.

## Decision

This follow-up advances four Tier 3 boundaries:

- `T3-01` named-landmark location-only recovery: **PASS**.
- `T3-02` live USGS clustered-point overlay and visibility mutation: **PASS**.
- `T3-03` manual Dark/OpenTopoMap basemap switching and post-render status recovery: **PASS**.
- `T3-04` NOAA alert non-renderable/valid-empty boundary: **BLOCKED** for this exact model/task lane.

The exact configured `opencode-go / deepseek-v4.1-flash` lane was retained
throughout. No provider or model fallback was used.

## Source and runtime

- Branch: `develop`.
- Source boundary: `develop@5947bdd` plus the four scoped working-tree changes
  under test; the delivery commit is recorded in the repository history.
- Backend/frontend: `127.0.0.1:7059` / `127.0.0.1:4512`.
- Isolated data root: `runtimes/cache/test-runtime/validation-20260924-exact-lane`.
- Browser: Chrome extension tab at `http://127.0.0.1:4512/`.
- The Settings model probe returned `Verified` / `Native tool probe passed`
  before the live run. The successful USGS run also displayed `Agent model:
  Verified`.

## Defects fixed during validation

1. Named-landmark location-only routing changed the primary domain to
   `MAP_RENDERING` but retained a duplicate map-rendering secondary domain.
   That made the server-owned location recovery predicate reject the route
   before `apply_map_plan`. The normalizer now clears `secondary_domains`, and
   the focused backend regression asserts the normalized route.
2. A successful manual basemap render without a pending agent render context
   did not clear the previous render warning or restore the ready status. The
   ready branch now clears the warning and transient progress label, and a
   focused Angular regression covers the recovery.

## Browser-authoritative evidence

### T3-01: location-only recovery

The pre-fix request `Show me the Colosseum in Rome.` produced a location
transcript but no map and stopped with a blocked candidate. After the routing
fix, run `run_ccece153b1f243349cbc340378bbfc6a` completed the server-owned
location-map recovery. Chrome visibly showed the Colosseum-centered
OpenStreetMap map, OSM attribution, MapLibre attribution, and the transcript
stating that the map was ready. The visible text reported the resolved
coordinates `41.89094° N, 12.49190° E`.

The persisted render observation for map session
`candidate-14ac5521f755485f9978e4262960ed89` was `ready`; required sources,
required layers, and viewport checks were all true.

### T3-02: live USGS vector overlay

Request: `Show me active USGS water gauges around Austin, Texas.`

Run `run_1e8d9e3cf1a442d9b4d057dbf9abb24a` completed with evidence
`evidence_1f2d5805a6b042a1ab6b6125bab2a457`. The provider returned 48
features with `map_eligibility=renderable`. Chrome visibly showed the Austin
basemap, clustered gauge points, the `USGS Water Gauges` layer, clustered-point
legend, and `U.S. Geological Survey` attribution. The final transcript said
the map was verified and ready.

The layer checkbox was exercised in the same rendered session: accessibility
state changed from `1 of 1 visible` to `0 of 1 visible` and back to
`1 of 1 visible`; the rendered map remained available throughout.

### T3-03: basemap switching and recovery status

The rendered USGS session was switched to `Dark Basemap` and then
`OpenTopoMap Terrain`. Screenshots observed inline showed the darkened OSM
tiles and the terrain tiles with the corresponding selector values and
attribution. A prior render warning was not left behind after the successful
dark-basemap recovery; the final accessibility state showed `Tool activity 4
calls`, `Agent model: Verified`, and no `Needs attention` warning.

The browser-control surface did not expose filesystem screenshot export, so
this report records the inline visual observations and accessibility state
instead of inventing screenshot filenames.

### T3-04: NOAA boundary

Request: `Show me current NOAA weather alerts around Houston, Texas.`

Run `run_f37c2e4ef9914c63847d22365e575147` reached location resolution,
capability description, and provider execution. Evidence
`evidence_6049bdd608fa4823b33b0b087557552b` contained one NOAA Air Quality
Alert and `map_eligibility=not_renderable`. The first `apply_map_plan` was
rejected because the evidence was not renderable; a subsequent semantic
validation failure and a later tool-not-exposed response caused the agent to
stop after repeated invalid tool calls. The UI showed `The agent stopped after
repeated invalid tool calls`, no map, and `Needs attention`.

This is recorded as `BLOCKED`, not as a renderer PASS or a valid-empty PASS.
The unchanged exact model/task combination should not be retried until either
the provider returns a genuine valid-empty result or the supported model/task
handling for non-renderable alerts is changed and revalidated.

## Focused checks

| Check | Result |
| --- | --- |
| Backend `test_capability_router.py` | `27 passed` (one existing protected-cache warning) |
| Frontend `geospatial-page.component.spec.ts` | `48 passed` under `CI=1` to disable the protected Angular local cache |
| Ruff on changed Python module | `All checks passed` with `--no-cache` |
| `git diff --check` | Passed; only normal LF-to-CRLF working-copy warnings |

The initial Angular run without the local-cache override hit an ACL-protected
`runtimes/cache/angular` file. Re-running with the repository's documented
isolated-cache pattern (`CI=1`, with the npm cache rooted under
`runtimes/cache`) passed; this is an environment limitation, not a product
failure.

The pushed source/evidence head `9b34c5aa52dd6c26c9c451d0d3384fa660e5893d`
passed all four hosted-CI jobs in [GitHub Actions run
36241506428](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36241506428).

## Cleanup

The task-owned backend PID `35368` and frontend PID `9856` were stopped only
after verifying their executable paths. Ports `4512`, `7059`, and `9876` were
then verified free. The user-owned Chrome tab was left open, and the isolated
runtime was retained for the recorded evidence.

## Remaining boundaries

`T3-05` through `T3-18` remain `UNRUN`. The complete route/provider matrix,
public FEMA/ESA raster loading, FEMA plus USGS composition and retention,
other raster families, ingestion, credentialed/local sources, and Tier 4/5
campaign slices remain open. The existing FEMA/ESA limitation remains a
separate `PARTIAL`/`BLOCKED` boundary; successful USGS and basemap rendering
does not promote it.
