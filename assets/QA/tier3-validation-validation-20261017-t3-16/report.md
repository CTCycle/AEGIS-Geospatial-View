# T3-16 and previously partial gates

Last updated: 2026-10-17

`T3-16` is **PASS** for its documented basemap/control scenarios.
`T4-04` advances from **PARTIAL to PASS** for GTFS static/realtime parsing and
configured live-feed validation. The wider routing, state-preservation,
ingestion, raster, and complete-matrix components remain **PARTIAL**.

## Tested boundary

- Branch `validation`, base `7faf0c1e778c7cf19f6f55177002e079f29a9733`, plus
  the four source/test changes fingerprinted in [slice.json](slice.json).
- Existing `app/server/.venv`; current Angular production build verified by
  its build fingerprint. No dependency installation or worktree.
- In-app Browser, isolated backend `127.0.0.1:5079`, disposable data beneath
  `runtimes/cache/test-runtime`. The existing keeper persisted exactly
  `opencode-go / deepseek-v4.1-flash` through Settings and obtained a passed,
  complete native structured probe. No fallback.
- Credentials were resolved in-process; neither credentials nor private
  reasoning were exported. Canonical database and settings files were not edited.

## T3-16 browser results

| Required scenario | Result | Evidence |
| --- | --- | --- |
| Liberty basemap | PASS: visible Rome tiles and OpenFreeMap/OpenMapTiles/OSM attribution | [Liberty](screenshots/liberty.png) |
| Positron basemap | PASS: distinct grayscale tiles and attribution | [Positron](screenshots/positron.png) |
| Satellite, identity, acknowledgement | PASS: fresh chat explicitly requested `esri_world_imagery`; native candidate has that exact ID, browser shows satellite pixels and Esri attribution, accepted ready observation for the same session/version | [Satellite](screenshots/satellite-identity.png), [run evidence](run-evidence.json) |
| Manual preference through overlay add/remove | PASS: Positron remained selected while the atmospheric point was added and removed; both runs received ready acknowledgements | [Add](screenshots/positron-atmosphere.png), [remove](screenshots/positron-removed.png) |
| Manual preference through location change | PASS: Rome to Milan retained Positron | [Milan](screenshots/positron-milan.png) |
| Reload/new chat reset | PASS: reload restored the committed Milan map on OSM; after selecting Liberty and starting a new chat, Paris rendered on OSM | [Reload](screenshots/reload-default.png), [new chat](screenshots/new-chat-default.png) |

Satellite identity run: `run_9d5aac855acf40b2a07052c6beaa6fa4`,
`candidate-38e52b12f847455f9eabdfb83383575a`, collection revision `0`.
The observation reports `required_sources_loaded=true`,
`required_layers_present=true`, `viewport_valid=true`, and `status=ready`.
Liberty/Positron manual selector operations do not create backend chat runs;
their visible rendering is documented separately from native acknowledgements.
The earlier [Colosseum run](screenshots/satellite-colosseum.png) retained a manually selected satellite style over a
server OSM candidate; it is supporting visual evidence, not the satellite
identity proof. The fresh explicit-ID run above closes that distinction.

An initial location-only Rome request failed because render preparation
overwrote a satisfied viewport obligation with the absence of provider data.
`render_completion.py` now applies the data-evidence spatial override only
when the contract actually requires evidence. Data requests still require
their evidence assessment. The parameterized regression covers both cases;
Rome, Milan, Paris, and explicit satellite requests pass live after the fix.
See [initial failure](screenshots/rome-before.png).

## Previously partial gates

| Gate/component | Current result and remaining boundary |
| --- | --- |
| T4-04 mobility | **PASS**, scoped to static/realtime adapters and configured-source validator. BART returned 287 stops, 14 routes, 28 shapes; MBTA returned 382 vehicles in the final validator run. Zero skipped checks and zero errors. Fixture/staleness/alert regressions also pass. This does not certify agent routing, a browser transit map, or cross-agency schedule/vehicle matching. |
| T4-03 heavy formats | **PARTIAL**. All five optional packages remain absent. More importantly, `execute_ingestion_plan` only normalizes CSV/GeoJSON: every other format unconditionally follows the warning/raw-artifact path. Installing the extra alone cannot close this gate; actual optional normalizers and real-source acceptance remain necessary. |
| T4-05 local/configured sources | **PARTIAL**. Current local materialization tests pass. Overture and OCM catalog availability still requires a configured index/snapshot or OCM credential; the parcel manifest remains a template with disabled health. No user-owned jurisdiction dataset was invented or modified. The existing failed-ingestion rollback limitation remains open. |
| ROUTE-LIVE / ISSUE-006 | **PARTIAL**. Fresh imagery request fails `temporal_scope_applied`, then makes invalid recovery calls. Numeric elevation remains disabled; its SRTM alternative times out and discovery ends empty. Census is now available in the runtime catalog, superseding the old disabled-capability diagnosis: both cartographic and TIGERweb requests reach execution but time out; alternate discovery consumes the execution budget. |
| GEO-FOCUS-16 / RASTER-LIVE / EEA | **PARTIAL**. Same-origin tile probe returns clean 502; backend diagnostics identify upstream HTTP 404 from the unchanged 2019 EEA service. No 2022 dataset was substituted for the requested 2019 layer. T3-15 remains deferred/unrun. |
| maps.state-preservation | **PARTIAL**. Actual manual preference persists, but backend narration says OpenStreetMap while the browser shows Positron. The manual preference is client-local, while the server candidate remains OSM. This distinct synchronization/narration limitation is not concealed by T3-16's control/render PASS. FEMA scale-dependent composition remains a separate prior limitation. |
| LIVE-DIARY / LIVE-HYD / MATRIX-22, broad recovery and provider coverage | **PARTIAL**, retaining their prior scope. This run adds the basemap and configured-GTFS slices; it does not execute their entire matrices. VISION-INSPECT remains UNRUN; no alternate vision-model lane was substituted. |

The GTFS live check exposed a validator defect: the realtime smoke declaration
required raw `entities`, although `GTFSRealtimeProvider` returns normalized
`vehicles`, `alerts`, `tripUpdates`, and `summary`. The declaration now checks
the actual contract. A real protobuf-parser/registry regression protects it;
the configured production validator then passes both real feeds.

Current route screenshots: [imagery](screenshots/imagery-partial.png),
[numeric elevation](screenshots/elevation-partial.png), and
[Census](screenshots/census-partial.png).

BART's stable download URL returned a 307 to its dated same-host archive;
production transport intentionally rejects redirects. The probe uses that
observed official archive directly. MBTA's official feed URL is unchanged.
The URLs and counts are in [partial-ingestion-probe.json](partial-ingestion-probe.json).
Feed provenance: [BART developer program](https://www.bart.gov/about/developers)
and [MBTA developer documentation](https://www.mbta.com/developers/gtfs-realtime).
Feed settings existed only in the probe subprocess and were not persisted.

Overpass was tried as a basemap lifecycle partner before Open-Meteo: Cortina
ended without an eligible alternative, and the explicit Colosseum-radius
request records a provider transport timeout. The last good map survived both.
These transient provider failures are retained in the run evidence; T3-12's
historical result is not presented as a current universal provider guarantee.

## Verification and evidence

- Full backend unit suite: **1,088 passed**, two existing upstream warnings;
  [final log](backend-unit-final.log).
- Ruff on all four edited source/test files: **PASS**; [log](ruff.log).
- Full strict Pyright configuration: **0 errors, 0 warnings, 0 informations**;
  [log](pyright.log).
- Angular production rebuild completed; the recorded source/output fingerprint
  is current. No frontend source changed; no new UI test suite was added.
- The first full unit run found a pre-existing root `.ruff_cache` dating to
  October 1. Its resolved location and cache-only contents were verified, it
  was removed, and the complete suite was rerun successfully. Protected cache
  residue elsewhere was preserved.
- [Run evidence](run-evidence.json) contains bounded map identities, native
  requirements, tool outcomes, render observations, and terminal results.
  No raw checkpoints or model reasoning were retained.
- Browser warning/error log query returned no entries at final capture;
  this is the available tool buffer, not an independent full network audit.
  Network evidence is bounded to proxy logs, the EEA probe, and accepted render
  observations. The browser tool did not export a request-by-request HAR.
- No hosted CI, commit, push, release, or provider-parity claim is made.
- The repository ignores `assets/QA/**`; include this curated package explicitly
  if a later authorized commit is made.

## Cleanup

The keeper's STOP mechanism shuts down the task backend and removes its owned
data root. Final port, owned-runtime, protected-file hash, build-state, and
artifact-integrity checks are recorded in [slice.json](slice.json).
