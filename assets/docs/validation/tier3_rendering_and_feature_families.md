# Tier 3 rendering and geospatial feature families

Last updated: 2026-10-01

Tier 3 is the rendering and geospatial feature-family gate. It must establish
browser-authoritative evidence that basemaps, vector/raster families,
valid-empty behavior, public providers, overlay mutation, composition, and map
inspection controls render and acknowledge correctly before Tier 4A ingestion,
Tier 4B provider parity, and Tier 5 recovery claims are expanded.

The first nine slices (`T3-01` through `T3-09`) were individually established
during execution and are `PASS`. Slices `T3-10` through `T3-18` were never
individually documented in the repository or its history; their IDs existed
only as inventory counts behind a single broad Tier 3 focus line. This document
reconstructs their acceptance criteria from repository evidence so a future
validation agent can execute each slice without rediscovering them.

## Reconstruction provenance and confidence

No `T3-10`–`T3-18` criterion was directly recovered from a historical source:
no deleted, renamed, or superseded document ever enumerated these IDs
(`git log --all -S` searches, the campaign-creation commit `9c2da7a4`, and the
QA consolidation `f3b819f2` were all checked). Every definition below is
reconstructed from multiple consistent sources or from the surrounding
architecture and is labeled accordingly:

- `MEDIUM` — the capability family is explicitly named as a remaining path in
  a ledger, report, or gate row, and the concrete mapping follows from the
  runtime catalog.
- `LOW` — the family or theme is named in the Tier 3 focus or a dated report,
  but the precise scenarios are inferred from neighboring gates.
- `UNRESOLVED` — evidence was insufficient to reconstruct reliably.

These statuses remain `UNRUN` until executed. Executing agents must record the
branch, exact SHA, environment, provider/model lane, and isolation boundary per
the [validation strategy](strategy.md), and must never promote an inference to
historical fact in evidence.

## Slice checklist

| Slice | Capability | Required boundary | Confidence | Primary evidence for the reconstruction |
| --- | --- | --- | --- | --- |
| `T3-10` | `usgs_earthquakes` | Live seismic clustered-point overlay, valid-empty, visibility mutation, remove/re-add | MEDIUM | `project_status_ledger.md` `maps.vector-overlays`; `data/catalog/overlays/usgs_earthquakes.json`; `app/server/services/geospatial/providers/usgs.py`; `T3-02` pattern |
| `T3-11` | `noaa_coops_water_levels`, `noaa_radar` | Remaining NOAA family: coastal station points and CONUS radar raster | MEDIUM (CO-OPS) / LOW (radar) | Ledger "coastal stations"; `noaa_coops_water_levels.json`/`noaa_radar.json`; `providers/noaa.py`; `tier3-remediation-20260930/report.md` |
| `T3-12` | `overpass_residential_buildings`, `overpass_poi_amenities` | Overpass building-footprint polygon and POI-amenity overlays | MEDIUM | Ledger "Residential buildings"; `providers/overpass.py`; manifests; `T2-03`/`T2-05` precedent |
| `T3-13` | `openmeteo_pressure_humidity_wind` | Open-Meteo atmospheric point family and numeric-insight-vs-map boundary | MEDIUM | Ledger "atmospheric points"; `providers/openmeteo.py`; manifest; route-matrix alias rows |
| `T3-14` | `gbif_species_occurrences` | GBIF biodiversity occurrence point-insight overlay with provenance/citation semantics | MEDIUM | `geospatial/providers/gbif.md`; manifest (keyless, clustered-points) |
| `T3-15` | `eea_noise_2019` | EEA public raster through the same-origin proxy to an accepted render acknowledgement | MEDIUM | `RASTER-LIVE`/`GEO-FOCUS-16` gate rows; route-matrix `eea_noise_milan`; `raster_tiles.py` |
| `T3-16` | `esri_world_imagery`, `openfreemap_liberty`, `openfreemap_positron` | Remaining basemap families and manual-preference persistence | LOW–MEDIUM | 2026-09-18/2026-09-19 diaries; basemap catalog enumeration; `T3-01`/`T3-03` pattern |
| `T3-17` | Mixed raster+vector overlay lifecycle | Raster+vector three-layer composition, opacity, ordering, selective removal, retain-across-change | LOW | 2026-09-18 deferred "raster-plus-vector three-layer stack"; `T3-06` pattern; `overlay-controls.component.*` |
| `T3-18` | `MapInspectionService`, overlay controls, evidence inspection, valid-empty recovery | Map inspection controls and family-wide valid-empty / non-renderable recovery | LOW | Tier 3 focus line "map inspection controls"; `app/server/services/geospatial/inspection.py`; `overlay-controls.component.*`; `T2-07`/`T3-04` precedent |

## Common execution contract

All Tier 3 slices share the standing campaign rules:

- Exact configured `opencode-go / deepseek-v4.1-flash` lane; **no fallback**.
- Disposable exact-lane backend (see `scripts/validation/run_t3_07_live_runtime.py`
  pattern; default port `5079`) with an isolated data root under
  `runtimes/cache/test-runtime/`; provider/model lane persisted through the
  Settings API and verified by the native structured probe
  (`provider=opencode-go`, `model=deepseek-v4.1-flash`, `parse_status=complete`).
- Browser-rendered state is authoritative: expected location/viewport, visible
  tiles, source/layer state, visible pixels where meaningful, attribution, and
  an accepted `map.render_ack` must be recorded when the workflow requires them.
- Manual-toggle overlays (`agenticUse.defaultEnabled:false`) must be enabled in
  Geospatial Access before their gate; a live browser run must not be promoted
  over an unverified renderer state.
- Every slice follows **Inspect -> Execute -> Observe -> Diagnose -> Surgically
  Fix -> Retest -> Record** and retains the browser evidence package listed in
  the strategy (`slice.json`, `browser-evidence.md`, `network-summary.json`,
  `backend.log`, `run-trace.json`, `api-response.json`, screenshots, notes).
- Status vocabulary: `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `UNRUN`.

## Per-gate execution contracts

### T3-10 — USGS Earthquakes live seismic overlay

- **Tier:** 3.
- **Purpose:** Validate the remaining USGS hazard vector family end-to-end
  (routing → provider retrieval → clustered-point render → acknowledgement),
  extending the point-overlay pattern of `T3-02` to the earthquake feed.
- **Capability/subsystem:** `usgs_earthquakes` (vector-overlay, GeoJSON Point,
  `renderingMode=clustered-points`, global coverage, keyless,
  `endpoint_health=functional`).
- **Preconditions:** `T3-01`–`T3-09` PASS; exact lane structured-probe ready;
  `usgs_earthquakes` enabled in Geospatial Access; USGS GeoJSON feed reachable.
- **Validation scenarios:**
  1. `Show recent earthquakes around Tokyo, Japan.` → resolve → route →
     execute → render clustered points → accepted ack.
  2. Valid-empty: a bounded region with no current events → `valid_empty`
     outcome, honest no-results overlay status, last-known-good map preserved.
  3. Visibility mutation: hide/show the layer.
  4. Remove and re-add the layer.
- **Expected behavior:** source+layer present, clustered points visible, USGS
  attribution, transcript "verified/ready", `map.render_ack` with
  `render_observed=ready`.
- **PASS:** all scenarios pass with browser-authoritative evidence.
- **PARTIAL:** e.g. render passes but the valid-empty boundary degrades into a
  failed tool loop (the historical `T3-04` failure shape).
- **FAIL:** a reproducible product defect (router rejects a valid seismic
  request; renderer never loads the source).
- **BLOCKED:** USGS feed outage, overlay disabled, or lane unready.
- **Environment:** local services, Chrome, isolated data root.
- **Provider/model lane:** `opencode-go / deepseek-v4.1-flash`, no fallback.
- **Credentials/datasets:** none (public feed).
- **Automated tests:** routing/manifest contract tests
  (`app/tests/unit/services/geospatial/test_agentic_manifest_contract.py`),
  USGS adapter tests, valid-empty unit coverage; a new E2E browser test modeled
  on `app/tests/e2e/test_live_gibs_raster_matrix.py`.
- **Browser/manual:** live Playwright run per scenario with screenshot/network/
  run-trace capture.
- **Evidence/artifacts:** `slice.json`, `report.md`, `browser-evidence.md`,
  `api-response.json`, `run-trace.json`, `network-summary.json`, `backend.log`,
  screenshots.
- **Depends on:** `T3-01`, `T3-02`, `T2-01`, `T2-03`.
- **Depended on by:** `T3-17`, `T3-18`.
- **Source files:** `app/server/services/geospatial/providers/usgs.py`,
  `data/catalog/overlays/usgs_earthquakes.json`,
  `app/client/src/app/components/overlay-controls.component.*`,
  `app/client/src/app/components/map-preview.component.ts`.
- **Historical documentation/QA evidence:** `project_status_ledger.md`
  `maps.vector-overlays` ("earthquakes … remain additional selected paths");
  `assets/QA/aegis-maps-geospatial-validation-20260918.md`; `T3-02` report.
- **Reconstruction confidence:** MEDIUM.

### T3-11 — NOAA coastal stations and radar (remaining NOAA family)

- **Tier:** 3.
- **Purpose:** Complete the NOAA family beyond alert geometry (`T3-04`):
  coastal water-level station points and the CONUS radar raster.
- **Capability/subsystem:** `noaa_coops_water_levels` (vector Point,
  manual-toggle, `endpoint_health=partial`) and `noaa_radar` (raster-overlay,
  manual-toggle, `partial`).
- **Preconditions:** `T3-04` PASS; exact lane; both overlays enabled; NOAA
  services reachable.
- **Validation scenarios:**
  1. Coastal stations around a US coastline location → point render + NOAA
     attribution + accepted ack.
  2. Radar raster over a CONUS city → same-origin proxy transport → render →
     ack (current temporal mode).
  3. Valid-empty / no-data boundary per NOAA response.
- **Expected behavior:** same browser-authoritative boundary as `T3-10`; radar
  is a raster path through the same-origin proxy like `T3-07/08/09`.
- **PASS/PARTIAL/FAIL/BLOCKED:** as `T3-10`. The 2026-09-30 remediation
  recorded backend `502` for `noaa_radar` in the isolated environment, so the
  radar sub-scenario may be `BLOCKED`/`PARTIAL` until the network boundary
  resolves; it must never be promoted to a render PASS.
- **Environment / lane / credentials / tests / browser / evidence:** identical
  shape to `T3-10`; NOAA public endpoints.
- **Depends on:** `T3-04`, `T3-10`.
- **Depended on by:** `T3-17`.
- **Source files:** `app/server/services/geospatial/providers/noaa.py`,
  `data/catalog/overlays/noaa_coops_water_levels.json`,
  `data/catalog/overlays/noaa_radar.json`.
- **Historical documentation/QA evidence:** `project_status_ledger.md`
  "coastal stations … remain additional selected paths";
  `tier3-remediation-20260930/report.md` (radar proxy observation).
- **Reconstruction confidence:** MEDIUM for CO-OPS; LOW for the radar
  sub-scenario (the explicit wording names only coastal stations).

### T3-12 — Overpass building footprints and POI amenity overlays

- **Tier:** 3.
- **Purpose:** Validate Overpass polygon rendering (residential building
  footprints) and the POI-amenity layer in the map session. POI *text* results
  are proven (`T2-05`) and a POI *layer* render is partially proven (`T2-03`);
  building-footprint polygon rendering is new.
- **Capability/subsystem:** `overpass_residential_buildings` (geojson Polygon,
  `defaultEnabled:true`, functional) and `overpass_poi_amenities` (point-insight,
  manual-toggle).
- **Preconditions:** `T2-03`/`T2-05` PASS; exact lane; Overpass reachable; note
  the documented "partial general reliability" and approximately 2.5 km result
  extent.
- **Validation scenarios:**
  1. Residential buildings around a city → polygon render + OSM attribution +
     accepted ack.
  2. POI-amenity layer render + visibility mutation.
  3. Remove/re-add.
  4. An honest no-results or provider-partial outcome is not promoted to a
     renderer success.
- **Expected behavior:** source/layer visible, attribution present, accepted
  ack; the provider's partial-reliability note is preserved in the transcript.
- **Depends on:** `T2-03`, `T2-05`, `T3-02`.
- **Depended on by:** `T3-17`.
- **Source files:** `app/server/services/geospatial/providers/overpass.py`,
  `data/catalog/overlays/overpass_residential_buildings.json`,
  `data/catalog/overlays/overpass_poi_amenities.json`.
- **Historical documentation/QA evidence:** `project_status_ledger.md`
  "Residential buildings … remain additional selected paths"; `T2-03`/`T2-05`
  reports; `ISSUE-001`.
- **Reconstruction confidence:** MEDIUM.

### T3-13 — Open-Meteo atmospheric point insight family

- **Tier:** 3.
- **Purpose:** Validate the atmospheric point layer (`pressure/humidity/wind`)
  and its numeric-insight-vs-map boundary; weather/AQ *text* is proven (`T2-05`,
  route-matrix), elevation is a tracked PARTIAL — this gate targets the
  remaining atmospheric family.
- **Capability/subsystem:** `openmeteo_pressure_humidity_wind`
  (time-series-insight point, `defaultEnabled:false`; confirm whether it is
  manually toggleable — the manifest shows `manualToggle:false`, so verify the
  enablement path before execution).
- **Preconditions:** `T2-05` PASS; exact lane; capability enabled/reachable;
  Open-Meteo reachable.
- **Validation scenarios:**
  1. Atmospheric conditions around a city → point overlay + legend +
     attribution + accepted ack.
  2. The direct-tool/text vs map boundary stays correct (no
     `unexpected_map_rendered` for a pure insight question).
  3. Valid-empty/partial semantics per Open-Meteo response.
- **Expected behavior:** same browser-authoritative boundary; partial-reliability
  and units preserved.
- **Depends on:** `T2-05`, `T3-10`.
- **Depended on by:** `T3-17`.
- **Source files:** `app/server/services/geospatial/providers/openmeteo.py`,
  `data/catalog/overlays/openmeteo_pressure_humidity_wind.json`.
- **Historical documentation/QA evidence:** `project_status_ledger.md`
  "atmospheric points … remain additional selected paths"; route-matrix report
  (Open-Meteo alias rows).
- **Reconstruction confidence:** MEDIUM.

### T3-14 — GBIF species occurrence point-insight overlay

- **Tier:** 3.
- **Purpose:** Validate the public biodiversity occurrence overlay (keyless,
  agent-reachable by default) with provenance/citation semantics.
- **Capability/subsystem:** `gbif_species_occurrences` (point-insight,
  `clustered-points`, global, `auth=none`, `endpoint_health=validated-by-official-contract`).
- **Preconditions:** exact lane; GBIF occurrence API reachable; non-antimeridian
  bounding box; bounded `limit` (AEGIS default 100, GBIF maximum 300).
- **Validation scenarios:**
  1. Species occurrences around a region → clustered points + `GBIF.org`
     attribution + dataset-level provenance + accepted ack.
  2. Sampled/total-match marking when results exceed the interactive page.
  3. Valid-empty / no-observations boundary.
  4. An occurrence result must not be presented as evidence of species absence.
- **Expected behavior:** source/layer/pixels/attribution/ack; provenance fields
  (`basisOfRecord`, `eventDate`, `datasetKey`) preserved.
- **Depends on:** `T3-02`, `T2-05`.
- **Depended on by:** `T3-17`.
- **Source files:** `app/server/services/geospatial/providers/gbif.py`,
  `data/catalog/overlays/gbif_species_occurrences.json`,
  `assets/docs/geospatial/providers/gbif.md`.
- **Historical documentation/QA evidence:** `geospatial/providers/gbif.md`;
  manifest health.
- **Reconstruction confidence:** MEDIUM (not listed in the explicit "remaining
  paths" sentence, so not HIGH).

### T3-15 — EEA public raster (noise) family

- **Tier:** 3.
- **Purpose:** Validate the last remaining public raster provider family (EEA
  noise) through the same-origin AEGIS tile proxy to an accepted render
  acknowledgement.
- **Capability/subsystem:** `eea_noise_2019` (WMS raster, EU-EEA coverage,
  keyless, manual-toggle; upstream **retired** — `noise.discomap.eea.europa.eu`
  2019 WMS returns 404).
- **Preconditions:** **manifest re-pointed** to the current EEA noise service
  (`noise.eea.europa.eu` / `portal.discomap.eea.europa.eu`, END-2022) — a
  recorded data-maintenance/product decision; the proxy already includes `eea`;
  exact lane.
- **Validation scenarios:**
  1. `Show noise exposure in Milan.` → route → provider retrieval →
     same-origin proxy transport (`direct_upstream_browser_request_count=0`) →
     render → accepted ack.
  2. EU-coverage guardrail: a non-EU request is rejected, not partially
     rendered.
- **Expected behavior:** proxy `200 image/png`, MapLibre source/layer/pixels,
  EEA attribution, accepted ack.
- **BLOCKED (current):** upstream retirement; record as `BLOCKED` until the
  manifest is re-pointed, exactly as `RASTER-LIVE`/`GEO-FOCUS-16` do today.
- **Depends on:** `T3-07` (proxy/render pattern), `T3-08`.
- **Depended on by:** `T3-17` (raster composition partner).
- **Source files:** `app/server/services/geospatial/providers/eea.py`,
  `data/catalog/overlays/eea_noise_2019.json`,
  `app/server/services/geospatial/raster_tiles.py`.
- **Historical documentation/QA evidence:** route-matrix report
  (`eea_noise_milan` row), `RASTER-LIVE` gate row, ecosystem audit
  `eea-noise-upstream-service`/`upstream_unavailable`.
- **Reconstruction confidence:** MEDIUM.

### T3-16 — Remaining basemap families (Esri imagery, OpenFreeMap Liberty/Positron)

- **Tier:** 3.
- **Purpose:** Cover the 3 of 6 catalog basemaps not exercised by `T3-01`
  (OSM) / `T3-03` (Dark, OpenTopoMap): satellite imagery and the Liberty/
  Positron styles, plus manual-preference persistence across overlay-active
  state and reload.
- **Capability/subsystem:** basemaps `esri_world_imagery`,
  `openfreemap_liberty`, `openfreemap_positron`.
- **Preconditions:** `T3-01`/`T3-03` PASS; exact lane; imagery style reachable
  (note `arcgis` is a credentialed provider in the catalog, and the
  `imagery_extent_rome` route is a tracked PARTIAL — confirm the egress/
  credential boundary for satellite before claiming a render).
- **Validation scenarios:**
  1. Liberty render + attribution.
  2. Positron render + attribution.
  3. Satellite imagery basemap render + accepted ack, or an honest boundary
     classification.
  4. Manual preference persists across overlay add/remove and location changes.
  5. Reload/new-chat resets to the catalog default by design (documented).
- **Depends on:** `T3-01`, `T3-03`, `T3-02`.
- **Depended on by:** none directly (feeds `T3-18` inspection).
- **Source files:** `data/catalog/basemaps/*`,
  `app/client/src/app/components/map-preview.component.ts` (style/selector
  contract).
- **Historical documentation/QA evidence:**
  `aegis-maps-geospatial-validation-20260918.md` (Liberty/Positron/Satellite
  exercised), `aegis-geospatial-e2e-validation-20260919` (satellite narration
  defect), `maps.basemap-switching` ledger row.
- **Reconstruction confidence:** LOW–MEDIUM.

### T3-17 — Mixed raster+vector composition and three-layer overlay lifecycle

- **Tier:** 3.
- **Purpose:** Extend `T3-06` vector-only composition to a true raster+vector
  stack with per-layer opacity/ordering, selective removal, and
  retain-across-change.
- **Capability/subsystem:** overlay lifecycle across families (for example GIBS
  raster + USGS vector + Census vector). Explicitly **not** FEMA-based:
  `T3-07` proved FEMA+partner single-viewport composition is limited by NFHL
  layer-28 scale-dependency.
- **Preconditions:** `T3-06`, `T3-08`, and at least the vector gates `T3-10`/
  `T3-12` PASS; a raster that renders in the same viewport as vector partners
  (GIBS `IMERG`/MODIS, or EEA post re-point).
- **Validation scenarios:**
  1. Add a raster over a vector layer → both visible, both attributed,
     accepted ack.
  2. Three layers (raster + two vector).
  3. Opacity slider mutation per layer.
  4. Selective removal retains the other layers.
  5. Remove the raster retains the vector layers and vice versa.
- **Depends on:** `T3-06`, `T3-08`, `T3-10`–`T3-14`, and a rendered raster
  partner (`T3-15` or `T3-08`).
- **Depended on by:** `T3-18`.
- **Source files:** `app/client/src/app/components/map-preview.component.ts`,
  `overlay-controls.component.*`,
  `app/server/services/agent/completion.py` (temporal/static composition
  contract).
- **Historical documentation/QA evidence:** 2026-09-18 deferred "true
  raster-plus-vector three-layer stack"; `T3-06` report; overlay-controls
  opacity/ordering surface.
- **Reconstruction confidence:** LOW.

### T3-18 — Map inspection controls and family-wide valid-empty / non-renderable recovery

- **Tier:** 3.
- **Purpose:** Validate the Tier 3 "map inspection controls" theme (the last
  focus keyword not yet covered) and the generic valid-empty / non-renderable
  recovery boundary across providers.
- **Capability/subsystem:** `MapInspectionService`
  (`app/server/services/geospatial/inspection.py`), `overlay-controls` component
  (per-layer `data-render-status`, `loaded`/`no-results`/`pending` states,
  opacity/visibility), attribution panel, `inspect_evidence` tool, valid-empty
  semantics, last-known-good preservation.
- **Preconditions:** `T2-07` (evidence inspection), `T3-04` (valid-empty), and
  the `T3-10`–`T3-14` family gates PASS.
- **Validation scenarios:**
  1. Overlay panel reflects committed state (`X of Y visible`, per-layer render
     status, opacity).
  2. A no-results overlay shows an honest valid-empty status without corrupting
     the map.
  3. An unsupported capability request ends in an explicit rejection with the
     last-known-good map preserved.
  4. Evidence inspector returns provenance for a rendered layer.
  5. Non-renderable data is classified data-only/PARTIAL and never promoted to
     a renderer success.
- **Expected behavior:** inspection read-backs always reflect the committed
  overlay collection, never a model claim (matches `HIST-004`).
- **Depends on:** `T2-07`, `T3-04`, `T3-10`–`T3-16`, `T3-17`.
- **Depended on by:** none within Tier 3.
- **Source files:** `app/server/services/geospatial/inspection.py`,
  `app/client/src/app/components/overlay-controls.component.ts/html`,
  `app/tests/e2e/test_map_render_regressions.py`,
  `app/tests/e2e/test_agentic_map_completion.py`.
- **Historical documentation/QA evidence:** Tier 3 focus line names "map
  inspection controls"; `T2-07` report; `T3-04` report; provider-framework
  `valid_empty` contract.
- **Reconstruction confidence:** LOW — the scenarios for this gate most need an
  upstream review before execution.

## Tier 4B and Tier 5 status

- Tier 4B (`T4-09`–`T4-13`) maps one gate per provider lane in the order stated
  by the strategy: `T4-09` OpenCode Go, `T4-10` OpenAI, `T4-11` Google,
  `T4-12` DeepSeek/OpenCode Zen, `T4-13` Ollama. The ID-to-lane mapping is
  recoverable at HIGH confidence from `strategy.md`; the per-lane acceptance
  text (provider-specific continuation plus structured-output probe) is not
  preserved and must be authored before execution.
- Tier 5 (`T5-01`–`T5-13`) has a cardinality defect: `strategy.md` lists 12
  themes ("Acknowledgement identity, failed-render recovery, races, outages,
  restart recovery, repetition, malformed input, cancellation, performance,
  accessibility, provider reconciliation, hosted CI") for 13 gates. The 13th
  ID is unmapped and remains `UNRESOLVED`. The `CONTROLLED-FAULT` matrix
  (happy, failed-layer, viewport mismatch, stale/duplicate ack, mismatched ack,
  cancellation, supersession, retry exhaustion) supplies the recovery-case
  granularity that likely maps to the early `T5` IDs, but the 1:1 assignment
  cannot be recovered. Do not execute Tier 5 without first resolving this
  mismatch.

## Next actionable slice

The T3-10..T3-14 keyless campaign is complete (all five slices `PASS`,
2026-10-01, including the NOAA radar proxy remediation for `T3-11`). The next
open Tier 3 slices are `T3-15` (EEA public raster, currently `BLOCKED` on the
retired `noise.discomap.eea.europa.eu` 2019 WMS until the manifest is
re-pointed), then `T3-16` (basemap families), `T3-17` (mixed raster+vector
composition), and `T3-18` (map inspection controls). Reuse the exact-lane
browser harness (`app/tests/e2e/test_live_vector_point_matrix.py`) and record
each slice per the strategy evidence package and status vocabulary.