# Native Agent Validation Gate Ledger

Last updated: 2026-09-26 (`T3-01`/`T3-02`/`T3-03` PASS; `T3-04` BLOCKED after the current exact-lane browser run; `T0-04` remains PARTIAL only for the safe historical timing comparator; source tested at `develop@5947bdd` plus scoped changes)

This is the canonical current-status source for the native-agent loop,
geospatial routing, durable map presentation, browser recovery harness,
provider lane, migrations, and hosted-CI boundary. Status values are limited
to `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, and `UNRUN`.

2026-09-19 live-browser diary checkout: `77bf7e999a58a53fd6fbe99bee5c01b5d96060dc` on `loop-dev` (working tree; not committed or pushed).
Prior native-agent final tested repository head: `a33642a29c4353a760aac34bf1234b8121211da6` on `develop`.
Production behavior commit: `558f1966afc3cef4b6e755d4edfdc87dfd258c11`;
the final tested head adds only controlled-harness evidence capture and
documentation reconciliation.

## Comprehensive validation campaign

The long-term Tier 0–5 campaign is defined in the
[validation strategy](strategy.md). The dated ancestor reports remain
historical evidence. The current Tier 0 reconciliation was run on `develop`
from starting SHA `7e8b10d58aebf21f194a74bcc2307f9d8e08f15c` with isolated
data/cache roots; the complete package is the
[current Tier 0 report](../../QA/tier0-validation-develop-20260922/final/report.md).
The
[Tier 1 application-foundations baseline](../../QA/tier1-application-foundations-20260921/report.md)
remains historical evidence at exact `loop-dev` commit
`c615c5799e1d5fb01e0af0eccaab5c6490d554c0`. The latest focused continuation is
the [T1-02 report](../../QA/tier1-validation-develop-20260922/T1-02/report.md)
on the `develop` working tree based at `8375fe071823e7f844f6bb125d86d6ebf36b3110`.
Its five fingerprinted source files were subsequently committed at
`35d04f8399d0166d1a134ad9f45931bc15efda91`; the historical T1-02 test
boundary remains the originally reported working tree. The 2026-09-23
[T1-03 report](../../QA/tier1-validation-develop-20260923/T1-03/report.md)
continues from that clean `develop` commit with one fingerprinted transcript
spacing repair.
This campaign ledger is orthogonal to the native-agent rows below: a native
gate can pass while its broader application-foundation slice remains partial.

| Tier | Focus | Slice count | Campaign status | Evidence / hand-off |
| --- | --- | ---: | --- | --- |
| Tier 0 | Environment, schema, current-HEAD reconciliation | 5 | `PARTIAL` | The [2026-09-22 Tier 0 reconciliation](../../QA/tier0-validation-develop-20260922/final/report.md) passed all five on its tested boundary. The [current-head recheck](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) found and fixed the launcher's inherited `AEGIS_DATA_DIR` precedence; the fresh/warm data-root subset passes, while the broader `T0-04` startup slice remains `PARTIAL`. |
| Tier 1 | Application foundations | 12 | `PASS` | [Tier 1 checklist](tier1_application_foundations.md), [T1-10 continuation](../../QA/tier1-validation-develop-20260923/T1-10/report.md), [T1-09 continuation](../../QA/tier1-validation-develop-20260923/T1-09/report.md), [T1-07 continuation](../../QA/tier1-validation-develop-20260923/T1-07/report.md), [T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md), and [T1-02 continuation](../../QA/tier1-validation-develop-20260922/T1-02/report.md); 12 `PASS`. The 2026-09-21 [baseline ledger](../../QA/tier1-application-foundations-20260921/ledger.md) remains historical. |
| Tier 2 | Core agent workflows | 7 | `PASS` | `T2-01`/`T2-02`/`T2-03`, `T2-05`/`T2-06`/`T2-07`, and the 2026-09-25 `T2-04` inventory run are `PASS`. The bounded inventory completed five pages and 50 unique candidates under the approved isolated `max_model_calls=6` budget. See the [T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [inventory trace](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/inventory-run-trace.json), and [browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md). |
| Tier 3 | Rendering and geospatial feature families | 18 | `PARTIAL` | `T3-01`/`T3-02`/`T3-03` pass current browser-authoritative location, vector-overlay, visibility-mutation, and basemap checks; `T3-04` is blocked by the exact-lane NOAA non-renderable/tool-validation boundary. `T3-05`–`T3-18` remain unrun. See the [Tier 3 follow-up](../../QA/tier3-validation-develop-20260926-map-rendering/report.md). |
| Tier 4A | Ingestion, local sources, optional integrations | 8 | `UNRUN` | Use isolated data and approved credentials/snapshots. |
| Tier 4B | Model-provider parity | 5 | `UNRUN` | Never substitute provider or model. |
| Tier 5 | Recovery, races, difficult boundaries, hosted CI | 13 | `UNRUN` | Open only after lower-tier contracts are classified. |

Campaign-slice status is 26 `PASS`, 1 `PARTIAL`, 1 `BLOCKED`, and 40 `UNRUN`
of 68 slices. These are the latest per-slice classifications across their
linked source boundaries, not a common-commit campaign result. Tier 0 is
`PARTIAL` for its broader Windows startup slice; Tier 1 is `PASS`; Tier 2
has seven `PASS` slices. `T0-04` remains partial only for the safe historical
timing comparator. The current exact-lane
[T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md)
and [browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md)
record the completed inventory and startup boundaries; the earlier continuation
and the [2026-09-25 direct-tool report](../../QA/tier2-validation-develop-20260925-next-slices/report.md)
retains the location, coverage-guardrail, direct-tool, saved-history, and
evidence-inspection boundaries.

The local T1-10 credential slice passed on
`develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; its exact pushed-head CI
passed all four jobs. Tier 1 remains complete at 12 `PASS`. The current
Tier 2 passes `T2-01`/`T2-02`/`T2-03`, `T2-04`, and
`T2-05`/`T2-06`/`T2-07`. See the
[2026-09-24 continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md)
and [2026-09-25 direct-tool continuation](../../QA/tier2-validation-develop-20260925-next-slices/report.md),
plus the [T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md).

## Current ledger

### Current Tier 0 slice ledger

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence |
| --- | --- | --- | --- | --- | --- |
| `T0-01` | Static quality | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-02` | Current SQLite migration/schema | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-03` | Legacy Settings migration | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-03 report](../../QA/tier0-validation-develop-20260922/T0-03/report.md) |
| `T0-04` | Windows startup | `PARTIAL` | 2026-09-25 | `develop@800e0568` | [T0/T2 follow-up report](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [timing results](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/timing-results.md), [safety harness](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/launcher-safety-harness.json) | Fresh/warm readiness, simulated provider outage, changed-owner/PID-reuse protection, injected backend/frontend cleanup, canonical-state protection, and port cleanup pass. The sole remaining limitation is the unavailable safe historical before/after timing comparator. |
| `T0-05` | API composition and contract | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-05 report](../../QA/tier0-validation-develop-20260922/T0-05/report.md) |

Tier 1 is `PASS`; Tier 0 is `PARTIAL` only because the safe historical Windows
startup timing comparator remains unavailable. The overall campaign is
`PARTIAL`: Tier 2 now has seven `PASS` slices; Tier 3 has three current
`PASS` slices and one exact-lane NOAA boundary `BLOCKED` after provider
execution returned a non-renderable alert and the model stopped after
repeated invalid tool calls. `T3-05`–`T3-18` and Tier 4–5 remain `UNRUN`, and
broader live/browser/provider boundaries remain partial or blocked. Historical
source and controlled matrix boundaries are retained below. The prior exact validation
source/test commit `a1b4e43ff20ab8683f34c04e9ff78e59dc01f74f` passed all four
hosted-CI jobs in [run 35970154295](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35970154295).

### Current Tier 1 continuation ledger

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `T1-02` | Frontend tab-local state | `PASS` | 2026-09-22 | `develop@8375fe071823e7f844f6bb125d86d6ebf36b3110` plus the source hashes recorded in the report; those source changes were later committed at `35d04f8399d0166d1a134ad9f45931bc15efda91` | [T1-02 report](../../QA/tier1-validation-develop-20260922/T1-02/report.md), [slice manifest](../../QA/tier1-validation-develop-20260922/T1-02/slice.json), [restored map controls screenshot](<../../QA/tier1-validation-develop-20260922/T1-02/screenshots/__test_refresh_same_tab_restores_chat_and_map_state[chromium]/t1-02-restored-map-state.png>) | Preserve its original boundary; the current campaign hand-off is `T2-01`. |
| `T1-03` | Conversation lifecycle and history | `PASS` | 2026-09-23 | `develop@35d04f8399d0166d1a134ad9f45931bc15efda91` plus the transcript CSS source hash recorded in the report | [T1-03 report](../../QA/tier1-validation-develop-20260923/T1-03/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-03/slice.json), [browser observations](../../QA/tier1-validation-develop-20260923/T1-03/browser-evidence.md) | `T1-10` is now passed; the current campaign hand-off is `T2-01`. |
| `T1-06` | Synchronous `/api/chat/turn` contract | `PASS` | 2026-09-23 | `develop@af663adaa5e14be3fcd7312e4bd230cca11f1b40`; source fingerprints are recorded in the report | [T1-06 report](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-06/slice.json), [redacted live HTTP matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json) | `T1-10` is now passed; the current campaign hand-off is `T2-01`. |
| `T1-07` | Background chat jobs | `PASS` | 2026-09-23 | `develop@3fd0c820c2d4de0fb06120b6feac80b199d57f26`; source fingerprints are recorded in the report | [T1-07 report](../../QA/tier1-validation-develop-20260923/T1-07/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-07/slice.json), [exact-lane job](../../QA/tier1-validation-develop-20260923/T1-07/live-job-evidence.json), [restart evidence](../../QA/tier1-validation-develop-20260923/T1-07/restart-evidence.json), [hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-07/hosted-ci.md) | `T1-10` is now passed; the current campaign hand-off is `T2-01`. |
| `T1-09` | Settings navigation and drafts | `PASS` | 2026-09-23 | `develop@c090abd1ca9d6d78e82e798da9167b9d19b3fc23`; source fingerprints are recorded in the report | [T1-09 report](../../QA/tier1-validation-develop-20260923/T1-09/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-09/slice.json), [source fingerprints](../../QA/tier1-validation-develop-20260923/T1-09/source-sha256.txt), [hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-09/hosted-ci.md) | `T1-10` is now passed; the current campaign hand-off is `T2-01`. |
| `T1-10` | Credential lifecycle | `PASS` | 2026-09-23 | `develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; source fingerprints are recorded in the report | [T1-10 report](../../QA/tier1-validation-develop-20260923/T1-10/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-10/slice.json), [hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-10/hosted-ci.md) | `T2-01` is the next campaign slice; the targeted model-selection regression does not expand the T1-11 boundary. |

### Current Tier 2 slice ledger

The 2026-09-25 follow-up used the exact configured OpenCode Go lane in
the isolated runtime. The provider probe passed after the final launcher restart.
Current browser run IDs, visible rendered states, acknowledgements, and
limits are in the [T0/T2 follow-up browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md)
and the earlier [continuation evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md).

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `T2-01` | Plain and ambiguous locations; Springfield clarification; invalid-coordinate retention; Italian-context Milan request | `PASS` | 2026-09-24 (exact-lane browser; 155 local regressions pass) | `develop@77c5d67` plus scoped changes | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [focused backend log](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log), [prior location evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md) | Milan now asks between canonical Texas and Lombardy candidates; explicit Italy renders and receives visible acknowledgement. Springfield clarification and invalid-coordinate retention remain supported by the linked prior evidence. |
| `T2-02` | Hydrated Rome to ambiguous Florence, then explicit Florence, Tuscany, Italy replacement | `PASS` | 2026-09-24 (exact-lane browser; 155 local regressions pass) | `develop@77c5d67` plus scoped changes | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [focused backend log](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log) | Ambiguous Florence was clarified while Rome remained displayed; selecting Tuscany rendered the correct location and received visible acknowledgement. |
| `T2-03` | Landmark and point-of-interest routing | `PASS` | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md) | Colosseum and clarified central-Rome POI flows resolved, retrieved, rendered, and acknowledged; preserve the partial-reliability and roughly 2.5 km Overpass coverage note. |
| `T2-04` | Capability discovery | `PASS` | 2026-09-25 | `develop@800e0568` | [follow-up report](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [slice manifest](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/slice.json), [inventory trace](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/inventory-run-trace.json), [focused suite](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log) | Five successful pages (`12+12+12+12+2`) reconciled to 50 unique candidates and `next_cursor=null` under the approved isolated `max_model_calls=6` budget. No map was requested or rendered; the original runtime setting was restored to `4` after restart. |
| `T2-05` | Direct tools: coordinates, weather, air quality, and filtered POI text results | `PASS` | 2026-09-25 | `develop@a712301` plus scoped working-tree changes | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md), [focused tests](../../QA/tier2-validation-develop-20260925-next-slices/report.md) | Tested exact-lane requests returned coordinates, 24 local hourly weather and AQ rows, and ten pharmacy-only Overpass rows without rendering a map. One AQ tool-argument rejection recovered on retry; Overpass’s general reliability remains partial and the response limit is ten. |
| `T2-06` | Conversation history hydration and saved map replay | `PASS` | 2026-09-25 | `develop@a712301` plus scoped working-tree changes | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md) | New browser tab after backend restart hydrated saved history and restored the transcript and Colosseum map. Crash recovery and all tab races were not tested. |
| `T2-07` | Saved evidence inspection | `PASS` | 2026-09-25 | `develop@a712301` plus scoped working-tree changes | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md) | Same-conversation inspector returned provenance and all ten categories with one call and no provider fetch or map plan. Saved-evidence map replay is recorded separately under `T2-06`; fresh chats without saved evidence do not receive the inspection-only route. |

### Current Tier 3 slice ledger

The 2026-09-26 follow-up uses the exact configured provider/model lane and
the isolated runtime. It advances the first three browser-authoritative map
rendering slices and records the next provider/model boundary without
converting a non-renderable provider result into a renderer success.

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `T3-01` | Named-landmark location-only recovery and basemap render | `PASS` | 2026-09-26 | `develop@5947bdd` plus scoped changes | [Tier 3 report](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [slice manifest](../../QA/tier3-validation-develop-20260926-map-rendering/slice.json) | Preserve the server-owned location recovery route and visible render acknowledgement while broadening landmark/provider coverage. |
| `T3-02` | Live USGS clustered-point overlay and visibility mutation | `PASS` | 2026-09-26 | `develop@5947bdd` plus scoped changes | [Tier 3 report](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [slice manifest](../../QA/tier3-validation-develop-20260926-map-rendering/slice.json) | Continue selected vector families and retain source/layer/attribution/render-ack evidence for each provider. |
| `T3-03` | Manual Dark/OpenTopoMap basemap switching and successful recovery status | `PASS` | 2026-09-26 | `develop@5947bdd` plus scoped changes | [Tier 3 report](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [slice manifest](../../QA/tier3-validation-develop-20260926-map-rendering/slice.json) | Keep the supported switch/recovery behavior distinct from public raster-family coverage; investigate any future source-specific load failures separately. |
| `T3-04` | NOAA alert non-renderable and valid-empty boundary | `BLOCKED` | 2026-09-26 | `develop@5947bdd` plus scoped changes | [Tier 3 report](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [slice manifest](../../QA/tier3-validation-develop-20260926-map-rendering/slice.json) | Reopen only with a genuine valid-empty provider result or a supported model/task handling change; do not retry the unchanged invalid-call boundary. |

| Gate ID / name | Subsystem | Lane / environment | Status | Verification date | Tested commit | Evidence link | Next action / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROUTE-UNIT - semantic catalog and alias contracts | Routing / catalog | Local focused native pytest | PASS | 2026-09-24 | `develop@77c5d67` plus scoped changes | [155 focused backend tests](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log), [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Capability routing, location resolution, Nominatim candidate labeling, tool contracts, and agent-loop regressions pass; preserve semantic subject matching, required aliases, generic-infrastructure clarification, and source-availability gates. |
| ROUTE-LIVE - exact-lane route matrix | Routing / catalog | Chrome UI, exact `opencode-go / deepseek-v4.1-flash` | PARTIAL | 2026-09-26 | `develop@5947bdd` plus scoped changes | [T0/T2 follow-up report](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [2026-09-25 T2 execution](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [Tier 3 browser evidence](../../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md) | Named-landmark location-only recovery and the live USGS route now pass in the current exact lane, but the broad matrix remains partial for Acropolis semantics, imagery extent, weather budget, aliases, generic-infrastructure clarification, provider coverage, NOAA handling, and other render families. |
| FEMA-COVERAGE-GUARDRAIL - declared extent rejection | Routing / coverage | Exact-lane Chrome UI, Zurich against FEMA NFHL | PASS | 2026-09-24 | `develop@77c5d67` plus scoped changes | [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Zurich resolved, capability description rejected the outside-coverage request, and the tool trace contains no provider retrieval or map render call. The attempted map request correctly ended blocked. |
| STATE-V2 — ConversationState and clarification projection | Agent state | Local focused native pytest plus isolated API checks | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep schema version 2 and `pending_clarification` as the sole durable/public contract; accept `unresolved_questions` only as migration input. |
| PRESENTATION-TERMINAL — terminal run finalization | Run persistence | Local backend unit/native tests | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Preserve atomic closure for failed, cancelled, superseded, and timed-out runs with no pending presentation row. |
| FINALIZATION-OBS — sanitized tools-disabled traces | Trace observability | Local focused native pytest | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current focused checks](../../QA/tier2-validation-develop-20260923-retry/report.md), [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Raw DSML finalization content is suppressed; keep reason, model call index, `tools_exposed=0`, and `tool_choice=none`; never persist private reasoning, credentials, or raw provider payloads. |
| RENDER-ADMISSION — renderer-safe map candidates | Execution / render | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Continue requiring usable vector/raster/GeoJSON descriptors before candidate admission. |
| CONTROLLED-HAPPY — visible MapLibre completion | Browser / MapLibre | Local Angular + backend, WebSocket fixture after real browser ack | PASS | 2026-09-24 | `develop@66008da15ea4ea23a5b1e99090441438bb163fba` | [exact-head completion screenshot](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/screenshots/__test_controlled_map_completion_requires_and_records_visible_rendering%5Bchromium%5D/controlled-map-completed.png), [scenario report](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/reports/controlled-map-completion.json), [full module](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Preserve real `map.render_ack` gating and visible completion; this is controlled evidence only. |
| CONTROLLED-FAULT — recovery and acknowledgement matrix | Browser / MapLibre | Local Angular app; WebSocket fixture injects only the controlled fault, MapLibre emits browser acknowledgements | PASS | 2026-09-24 | `develop@66008da15ea4ea23a5b1e99090441438bb163fba` | [full module: 10 passed](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log), [scenario reports](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/reports/), [recheck report](../../QA/tier2-validation-develop-20260924-head66008da/report.md) | The complete controlled suite passes, including supersession, stale acknowledgement, and retry exhaustion. This does not establish live public-raster loading or the complete provider/browser matrix. |
| PROVIDER-READY - exact configured lane readiness | Provider | `opencode-go / deepseek-v4.1-flash` | PASS | 2026-09-25 | `develop@800e0568` | [follow-up browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [historical structured probe](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final/http/CHAT-LIVE-01/provider-structured-probe.json) | After the final launcher restart, the exact model remained selected and the Settings probe returned `Verified` / `Native tool probe passed`. No fallback or provider switch occurred. |
| LIVE-BROWSER-SMOKE — realtime UI smoke | Browser / realtime | Local services 4512/7059, exact provider lane, isolated runtime data | PASS | 2026-09-26 | `develop@5947bdd` plus scoped changes | [live-browser-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final.log), [Tier 3 report](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md) | Current location-only, USGS overlay, layer mutation, and supported basemap switch checks pass; the smoke subset still is not complete 22-scenario proof and NOAA remains blocked for this lane. |
| LIVE-DIARY-20260919 - representative geospatial browser diary | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, real chat workflow | PARTIAL | 2026-09-24 | `develop@77c5d67` plus scoped changes | [current continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [prior T2 execution](../../QA/tier2-validation-develop-20260923-retry/report.md), [historical diary](../../QA/aegis-geospatial-e2e-validation-20260919/report.md) | Rome-to-Florence ambiguity now clarifies before map replacement, and Milan candidate labels are canonical with explicit Italy rendering. The wider diary remains partial for coordinate reverse geocoding, additional route families, and provider coverage. |
| LIVE-HYD-20260920 - hazard and hydrology rerun | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, live public providers | PARTIAL | 2026-09-26 | `84c210f6` plus current scoped browser evidence | [hazard/hydrology rerun](../../QA/aegis-hazard-hydrology-e2e-20260920/report.md), [Zurich coverage evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [current USGS/NOAA boundary](../../QA/tier3-validation-develop-20260926-map-rendering/report.md) | Current USGS gauges render and support visibility mutation. FEMA/ESA MapLibre source loading still fails; the current NOAA alert returned non-renderable evidence and stopped after invalid tool calls. `GEO-HYD-05` and `GEO-HYD-06` remain `BLOCKED`, so keep this gate partial. |
| LIVE-API — orchestration and ambiguity smoke | API orchestration | Exact provider lane, isolated runtime | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current live API recheck](../../QA/tier2-validation-develop-20260923-retry/live-api-recheck.json), [T1-06 historical live matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json), [historical API log](../../QA/native-agent-loop-evaluation-20260917-final/api-live-final.log) | Current exact-lane recheck returned 200 then 409 for a concurrent same-conversation request, with one terminal persisted run and isolated DB integrity `ok`. Keep the Ollama-unavailable `502` as a separate non-fallback boundary. |
| SYNC-CHAT-TURN — terminal hydration response | Backend API | Exact `opencode-go / deepseek-v4.1-flash` lane, isolated runtime, and focused API/OpenAPI pytest | PASS | 2026-09-23 | `develop@af663adaa5e14be3fcd7312e4bd230cca11f1b40` | [T1-06 report](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [live HTTP matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json) | Preserve terminal hydration, genuine-conflict, accepted-run details, preflight, and safe provider-error behavior. |
| BACKEND-UNIT - full unit suite | Backend | Standard Windows runner, isolated basetemp | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [local 932-test suite](../../QA/tier2-validation-develop-20260924-head77c5d67/post-cache-cleanup-full-unit.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | All 932 local unit tests pass with three existing warnings; the hosted backend suite also passes on the exact implementation commit. |
| OPENAPI-SCHEMA - generated shared API contract | Backend / frontend contract | Runtime schema export and exact equality test | PASS | 2026-09-25 | `develop@952e92721f45a6bc245dc4ed6271c5e32a01017b` | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [GitHub Actions run 36116073402](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36116073402) | Regenerated `app/shared/openapi.json` with the repository script; runtime equality passed in the 420-test backend suite and the exact-source hosted workflow. |
| NATIVE-FOCUSED - remediation regression suite | Backend / agent loop / catalog | `app/server/.venv`, isolated basetemp | PASS | 2026-09-25 | `develop@800e0568` | [83 focused checks](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log), [startup checks](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/startup-checks.log), [prior 155-check continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log) | Runtime-environment, startup/outage, capability-router, catalog-handler, and agent-loop checks pass; the full implementation boundary remains covered by the linked prior 155-check and 932-test suites. |
| RUFF - Python lint | Python quality | Repository backend and test packages | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [repository Ruff log](../../QA/tier2-validation-develop-20260924-head77c5d67/hosted-static-fix-ruff.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | All repository checks pass on the implementation source; the hosted strict static-analysis job is green. |
| PYRIGHT-STRICT - repository strict typing | Static typing | `app/server/pyproject.toml` strict run | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [local Pyright log](../../QA/tier2-validation-develop-20260924-head77c5d67/hosted-static-fix-pyright.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | Full repository run reports 0 errors, 0 warnings, and 0 informations on the current implementation. |
| FRONTEND-BUILD — production bundle | Angular client | Local `npm run build` via official launcher | PASS | 2026-09-23 | `develop@155e1e22ce34a4b2698f474afa60b57f61b56916` | [T2 validation report](../../QA/tier2-validation-develop-20260923/report.md) | The production bundle completed; backend readiness still blocked live browser validation. Keep generated `dist` output out of source control. |
| FRONTEND-KARMA — client regression suite | Angular client | ChromeHeadlessNoGpu | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | 248/248 pass; add browser-timing coverage before retrying supersession remediation. |
| MIGRATION — isolated upgrade/head/check | Persistence schema | Isolated SQLite under dated QA data | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Fresh upgrade, `alembic check`, `current --check-heads`, and 25 migration/persistence tests pass at `202609210001`. |
| MATRIX-22 - complete required scenario matrix | Coverage | Exact live provider plus controlled browser | PARTIAL | 2026-09-26 | `develop@5947bdd` plus scoped live evidence; controlled subset remains at `66008da15ea4ea23a5b1e99090441438bb163fba` | [T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [Tier 3 report](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [controlled module: 10 passed](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log), [original matrix report](../../QA/native-agent-loop-evaluation-20260917-final/final-report.md) | Location, USGS vector, supported basemap, and visibility-mutation scenarios pass. Broad route, multilingual, NOAA/non-renderable, raster/composition, provider-parity, recovery, and remaining Tier 3-5 rows remain open. |
| HOSTED-CI - exact pushed head | Hosted CI | GitHub Actions push workflow on `develop` | PASS | 2026-09-25 | `develop@db5b9485e80073f87dd4a8b964e484ba42384fcb` (evidence-only follow-up; source tested at `800e0568f6b83254b60c4efe25e014e3fefdf81c`) | [GitHub Actions run 36152093449](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36152093449), [hosted-CI evidence](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/hosted-ci-followup.md), [prior implementation run 36116073402](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36116073402) | All four jobs passed: backend units/static analysis/OpenAPI equality, SQLite persistence, capability contracts, and frontend build/unit/geospatial browser smoke. The pushed head contains only the reviewed validation evidence and ledger documentation. |
| PROCESS-CLEANUP - task-owned services and browser | Test harness | Local host, ports 4512/7059/9876 | PASS | 2026-09-26 | `develop@5947bdd` plus scoped validation | [Tier 3 cleanup evidence](../../QA/tier3-validation-develop-20260926-map-rendering/report.md), [prior cleanup checks](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/cleanup-checks.md) | Task-owned backend PID `35368` and frontend PID `9856` were path-verified and stopped; ports `4512`, `7059`, and `9876` were free. The user-owned Chrome tab was left open and the isolated runtime was retained for evidence review. |

## 2026-09-19 live browser diary

The representative browser run covered Lugano, Springfield, direct
coordinates, Mount Etna, Tokyo, overlay lifecycle actions, and the Rome to
Florence multi-turn path. The exact provider/model lane was visible in the UI;
the agent model reached `Verified` after the first successful request.

The most important reproducible defect was a hydrated multi-turn location
request that could repeat location resolution until the execution limit while
retaining the previous map. The working tree now invokes the existing typed
location-only `apply_map_plan` recovery after a successful location tool cycle
and no longer suppresses the same recovery for hydrated state. The focused
agent-loop suite is `35 passed`, and the browser retest rendered Florence after
a safe clarification, with header `Florence, Tuscany, Italy`, center
`11.2556°E, 43.7698°N`, verified render status, and two calls.

The diary remains `PARTIAL`: direct coordinate rendering passed but reverse
geocoding was unavailable; Mount Etna terrain/weather/catalog coverage was
not available; the MODIS request encountered a non-retryable upstream provider
failure; and assistant narration can still name OpenStreetMap after a manual
Satellite selection even when the rendered map state is correct. Cambridge,
typo, and multilingual rows were not run in this diary. See the [full
validation diary](../../QA/aegis-geospatial-e2e-validation-20260919/report.md)
for the scenario-by-scenario evidence and exact boundaries.

## Browser fault acceptance contract

The controlled fixture may inject only WebSocket responses after the browser has
sent its real `map.render_ack`. It must not add production fault flags,
endpoints, catalog entries, or render-admission branches. Each passing report
records the run ID/version, map session and revision, acknowledgement payloads,
event sequence, final UI state, screenshot, sanitized console output, and final
presentation status. The supersession report is intentionally absent because
its required assertion failed; the failure is retained in the test log.

## Update rule

Revise the smallest affected row when evidence changes. Keep `BLOCKED` and
`UNRUN` gates visible. Local, controlled, or synthetic results must not be
promoted to live-provider, hosted-CI, or complete-matrix proof.
