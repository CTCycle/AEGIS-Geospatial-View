# Native Agent Validation Gate Ledger

Last updated: 2026-09-25 (`T2-05`/`T2-06`/`T2-07` PASS on selected exact-lane scenarios; `T2-04` and `T0-04` remain PARTIAL; first exact-head CI run 36114905386 exposed strict typing errors now fixed locally; follow-up CI is pending publication)

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
| Tier 2 | Core agent workflows | 7 | `PARTIAL` | `T2-01`/`T2-02`/`T2-03` and the 2026-09-25 `T2-05`/`T2-06`/`T2-07` scenarios are `PASS`; `T2-04` remains `PARTIAL` after 36 inventory candidates across three pages hit `max_model_calls=4`. See the [2026-09-25 continuation](../../QA/tier2-validation-develop-20260925-next-slices/report.md) and [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md). |
| Tier 3 | Rendering and geospatial feature families | 18 | `UNRUN` | Require browser-authoritative source/layer/render-ack evidence. |
| Tier 4A | Ingestion, local sources, optional integrations | 8 | `UNRUN` | Use isolated data and approved credentials/snapshots. |
| Tier 4B | Model-provider parity | 5 | `UNRUN` | Never substitute provider or model. |
| Tier 5 | Recovery, races, difficult boundaries, hosted CI | 13 | `UNRUN` | Open only after lower-tier contracts are classified. |

Campaign-slice status is 22 `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 44 `UNRUN`
of 68 slices. These are the latest per-slice classifications across their
linked source boundaries, not a common-commit campaign result. Tier 0 is
`PARTIAL` for its broader Windows startup slice; Tier 1 is `PASS`; Tier 2
has six `PASS` and one `PARTIAL` slice. `T2-04` remains partial at the
configured model-call limit. The current exact-lane
[continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md)
and [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md)
record the location flows, inventory boundary, and Zurich coverage guardrail;
the [2026-09-25 continuation](../../QA/tier2-validation-develop-20260925-next-slices/report.md)
records direct tools, saved history, and evidence inspection.

The local T1-10 credential slice passed on
`develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; its exact pushed-head CI
passed all four jobs. Tier 1 remains complete at 12 `PASS`. The current
Tier 2 passes `T2-01`/`T2-02`/`T2-03` and `T2-05`/`T2-06`/`T2-07`;
`T2-04` remains `PARTIAL` at the configured model-call guard. See the
[2026-09-24 continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md)
and [2026-09-25 continuation](../../QA/tier2-validation-develop-20260925-next-slices/report.md).

## Current ledger

### Current Tier 0 slice ledger

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence |
| --- | --- | --- | --- | --- | --- |
| `T0-01` | Static quality | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-02` | Current SQLite migration/schema | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-03` | Legacy Settings migration | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-03 report](../../QA/tier0-validation-develop-20260922/T0-03/report.md) |
| `T0-04` | Windows startup | `PARTIAL` | 2026-09-24 | `develop@77c5d67` plus the launcher override fix | [T0-04 historical report](../../QA/tier0-validation-develop-20260922/T0-04/report.md), [current continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | The inherited non-empty data-root override passes fresh and warm starts; broader timing, provider-outage, ownership-race, and injected-failure cleanup remain unverified. |
| `T0-05` | API composition and contract | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-05 report](../../QA/tier0-validation-develop-20260922/T0-05/report.md) |

Tier 1 is `PASS`; Tier 0 is `PARTIAL` because Windows startup outage, race,
and injected-failure cleanup cases remain unverified. The overall campaign
is `PARTIAL`: Tier 2 currently has six `PASS` and one `PARTIAL` slice;
Tier 3–5 remain `UNRUN`, and broader live/browser/provider
boundaries remain partial or blocked. Historical source and controlled
matrix boundaries are retained below. The prior exact validation
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

The 2026-09-24 continuation used the exact configured OpenCode Go lane in
the isolated runtime. The provider probe passed after the launcher restart.
Current browser run IDs, visible rendered states, acknowledgements, and
limits are in the [continuation evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md).

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `T2-01` | Plain and ambiguous locations; Springfield clarification; invalid-coordinate retention; Italian-context Milan request | `PASS` | 2026-09-24 (exact-lane browser; 155 local regressions pass) | `develop@77c5d67` plus scoped changes | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [focused backend log](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log), [prior location evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md) | Milan now asks between canonical Texas and Lombardy candidates; explicit Italy renders and receives visible acknowledgement. Springfield clarification and invalid-coordinate retention remain supported by the linked prior evidence. |
| `T2-02` | Hydrated Rome to ambiguous Florence, then explicit Florence, Tuscany, Italy replacement | `PASS` | 2026-09-24 (exact-lane browser; 155 local regressions pass) | `develop@77c5d67` plus scoped changes | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [focused backend log](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log) | Ambiguous Florence was clarified while Rome remained displayed; selecting Tuscany rendered the correct location and received visible acknowledgement. |
| `T2-03` | Landmark and point-of-interest routing | `PASS` | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md) | Colosseum and clarified central-Rome POI flows resolved, retrieved, rendered, and acknowledged; preserve the partial-reliability and roughly 2.5 km Overpass coverage note. |
| `T2-04` | Capability discovery | `PARTIAL` | 2026-09-24 | `develop@77c5d67` plus scoped changes | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [slice manifest](../../QA/tier2-validation-develop-20260924-head77c5d67/slice.json), [focused backend log](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log) | Three 12-item pages (36/50) completed without requesting a map; continuation stopped at `max_model_calls=4`. Finish only with an approved budget adjustment or a continuation policy that honors the configured guard. |
| `T2-05` | Direct tools: coordinates, weather, air quality, and filtered POI text results | `PASS` | 2026-09-25 | `develop@a712301` plus scoped working-tree changes | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md), [focused tests](../../QA/tier2-validation-develop-20260925-next-slices/report.md) | Tested exact-lane requests returned coordinates, 24 local hourly weather and AQ rows, and ten pharmacy-only Overpass rows without rendering a map. One AQ tool-argument rejection recovered on retry; Overpass’s general reliability remains partial and the response limit is ten. |
| `T2-06` | Conversation history hydration and saved map replay | `PASS` | 2026-09-25 | `develop@a712301` plus scoped working-tree changes | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md) | New browser tab after backend restart hydrated saved history and restored the transcript and Colosseum map. Crash recovery and all tab races were not tested. |
| `T2-07` | Saved evidence inspection | `PASS` | 2026-09-25 | `develop@a712301` plus scoped working-tree changes | [2026-09-25 report](../../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md) | Same-conversation inspector returned provenance and all ten categories with one call and no provider fetch or map plan. Saved-evidence map replay is recorded separately under `T2-06`; fresh chats without saved evidence do not receive the inspection-only route. |

| Gate ID / name | Subsystem | Lane / environment | Status | Verification date | Tested commit | Evidence link | Next action / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROUTE-UNIT - semantic catalog and alias contracts | Routing / catalog | Local focused native pytest | PASS | 2026-09-24 | `develop@77c5d67` plus scoped changes | [155 focused backend tests](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log), [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Capability routing, location resolution, Nominatim candidate labeling, tool contracts, and agent-loop regressions pass; preserve semantic subject matching, required aliases, generic-infrastructure clarification, and source-availability gates. |
| ROUTE-LIVE - exact-lane route matrix | Routing / catalog | Chrome UI, exact `opencode-go / deepseek-v4.1-flash` | PARTIAL | 2026-09-24 | `develop@77c5d67` plus scoped changes | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [2026-09-23 T2 execution](../../QA/tier2-validation-develop-20260923-retry/report.md) | Milan and Rome-to-Florence location flows pass, but the broad matrix remains partial for Acropolis semantics, imagery extent, weather budget, USGS/land-cover aliases, generic-infrastructure clarification, and incomplete inventory discovery. |
| FEMA-COVERAGE-GUARDRAIL - declared extent rejection | Routing / coverage | Exact-lane Chrome UI, Zurich against FEMA NFHL | PASS | 2026-09-24 | `develop@77c5d67` plus scoped changes | [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Zurich resolved, capability description rejected the outside-coverage request, and the tool trace contains no provider retrieval or map render call. The attempted map request correctly ended blocked. |
| STATE-V2 — ConversationState and clarification projection | Agent state | Local focused native pytest plus isolated API checks | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep schema version 2 and `pending_clarification` as the sole durable/public contract; accept `unresolved_questions` only as migration input. |
| PRESENTATION-TERMINAL — terminal run finalization | Run persistence | Local backend unit/native tests | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Preserve atomic closure for failed, cancelled, superseded, and timed-out runs with no pending presentation row. |
| FINALIZATION-OBS — sanitized tools-disabled traces | Trace observability | Local focused native pytest | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current focused checks](../../QA/tier2-validation-develop-20260923-retry/report.md), [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Raw DSML finalization content is suppressed; keep reason, model call index, `tools_exposed=0`, and `tool_choice=none`; never persist private reasoning, credentials, or raw provider payloads. |
| RENDER-ADMISSION — renderer-safe map candidates | Execution / render | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Continue requiring usable vector/raster/GeoJSON descriptors before candidate admission. |
| CONTROLLED-HAPPY — visible MapLibre completion | Browser / MapLibre | Local Angular + backend, WebSocket fixture after real browser ack | PASS | 2026-09-24 | `develop@66008da15ea4ea23a5b1e99090441438bb163fba` | [exact-head completion screenshot](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/screenshots/__test_controlled_map_completion_requires_and_records_visible_rendering%5Bchromium%5D/controlled-map-completed.png), [scenario report](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/reports/controlled-map-completion.json), [full module](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Preserve real `map.render_ack` gating and visible completion; this is controlled evidence only. |
| CONTROLLED-FAULT — recovery and acknowledgement matrix | Browser / MapLibre | Local Angular app; WebSocket fixture injects only the controlled fault, MapLibre emits browser acknowledgements | PASS | 2026-09-24 | `develop@66008da15ea4ea23a5b1e99090441438bb163fba` | [full module: 10 passed](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log), [scenario reports](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/reports/), [recheck report](../../QA/tier2-validation-develop-20260924-head66008da/report.md) | The complete controlled suite passes, including supersession, stale acknowledgement, and retry exhaustion. This does not establish live public-raster loading or the complete provider/browser matrix. |
| PROVIDER-READY - exact configured lane readiness | Provider | `opencode-go / deepseek-v4.1-flash` | PASS | 2026-09-24 | `develop@77c5d67` plus scoped changes | [current browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [historical structured probe](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final/http/CHAT-LIVE-01/provider-structured-probe.json) | After launcher restart, the exact model remained selected and the Settings probe returned `Verified` / `Native tool probe passed`. No fallback or provider switch occurred. |
| LIVE-BROWSER-SMOKE — realtime UI smoke | Browser / realtime | Local services 4512/7059, exact provider lane, isolated runtime data | PASS | 2026-09-17 | `558f1966` | [live-browser-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final.log) | Four tests passed: three exact-lane UI flows plus one intentional degraded-path stub; do not promote this subset to complete 22-scenario proof. |
| LIVE-DIARY-20260919 - representative geospatial browser diary | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, real chat workflow | PARTIAL | 2026-09-24 | `develop@77c5d67` plus scoped changes | [current continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [prior T2 execution](../../QA/tier2-validation-develop-20260923-retry/report.md), [historical diary](../../QA/aegis-geospatial-e2e-validation-20260919/report.md) | Rome-to-Florence ambiguity now clarifies before map replacement, and Milan candidate labels are canonical with explicit Italy rendering. The wider diary remains partial for coordinate reverse geocoding, additional route families, and provider coverage. |
| LIVE-HYD-20260920 - hazard and hydrology rerun | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, live public providers | PARTIAL | 2026-09-24 | `84c210f6` plus current Zurich guardrail evidence | [hazard/hydrology rerun](../../QA/aegis-hazard-hydrology-e2e-20260920/report.md), [Zurich coverage evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md) | FEMA declared-coverage rejection passes for Zurich. Public FEMA/ESA MapLibre source loading still fails; `GEO-HYD-05` and `GEO-HYD-06` remain `BLOCKED`, so keep this gate partial. |
| LIVE-API — orchestration and ambiguity smoke | API orchestration | Exact provider lane, isolated runtime | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current live API recheck](../../QA/tier2-validation-develop-20260923-retry/live-api-recheck.json), [T1-06 historical live matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json), [historical API log](../../QA/native-agent-loop-evaluation-20260917-final/api-live-final.log) | Current exact-lane recheck returned 200 then 409 for a concurrent same-conversation request, with one terminal persisted run and isolated DB integrity `ok`. Keep the Ollama-unavailable `502` as a separate non-fallback boundary. |
| SYNC-CHAT-TURN — terminal hydration response | Backend API | Exact `opencode-go / deepseek-v4.1-flash` lane, isolated runtime, and focused API/OpenAPI pytest | PASS | 2026-09-23 | `develop@af663adaa5e14be3fcd7312e4bd230cca11f1b40` | [T1-06 report](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [live HTTP matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json) | Preserve terminal hydration, genuine-conflict, accepted-run details, preflight, and safe provider-error behavior. |
| BACKEND-UNIT - full unit suite | Backend | Standard Windows runner, isolated basetemp | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [local 932-test suite](../../QA/tier2-validation-develop-20260924-head77c5d67/post-cache-cleanup-full-unit.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | All 932 local unit tests pass with three existing warnings; the hosted backend suite also passes on the exact implementation commit. |
| OPENAPI-SCHEMA - generated shared API contract | Backend / frontend contract | Runtime schema export and exact equality test | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [local schema equality test](../../QA/tier2-validation-develop-20260924-head77c5d67/openapi-snapshot-pytest.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | Regenerated `app/shared/openapi.json`; runtime equality and the hosted diff check pass. |
| NATIVE-FOCUSED - remediation regression suite | Backend / agent loop / catalog | `app/server/.venv`, isolated basetemp | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [155 focused checks](../../QA/tier2-validation-develop-20260924-head77c5d67/focused-backend-final.log), [post-fix router checks](../../QA/tier2-validation-develop-20260924-head77c5d67/hosted-static-fix-pytest.log), [complete unit suite](../../QA/tier2-validation-develop-20260924-head77c5d67/post-cache-cleanup-full-unit.log) | Routing, location, ambiguity labeling, inventory pagination, native loop, and full backend tests pass on the final implementation boundary. |
| RUFF - Python lint | Python quality | Repository backend and test packages | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [repository Ruff log](../../QA/tier2-validation-develop-20260924-head77c5d67/hosted-static-fix-ruff.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | All repository checks pass on the implementation source; the hosted strict static-analysis job is green. |
| PYRIGHT-STRICT - repository strict typing | Static typing | `app/server/pyproject.toml` strict run | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [local Pyright log](../../QA/tier2-validation-develop-20260924-head77c5d67/hosted-static-fix-pyright.log), [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085) | Full repository run reports 0 errors, 0 warnings, and 0 informations on the current implementation. |
| FRONTEND-BUILD — production bundle | Angular client | Local `npm run build` via official launcher | PASS | 2026-09-23 | `develop@155e1e22ce34a4b2698f474afa60b57f61b56916` | [T2 validation report](../../QA/tier2-validation-develop-20260923/report.md) | The production bundle completed; backend readiness still blocked live browser validation. Keep generated `dist` output out of source control. |
| FRONTEND-KARMA — client regression suite | Angular client | ChromeHeadlessNoGpu | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | 248/248 pass; add browser-timing coverage before retrying supersession remediation. |
| MIGRATION — isolated upgrade/head/check | Persistence schema | Isolated SQLite under dated QA data | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Fresh upgrade, `alembic check`, `current --check-heads`, and 25 migration/persistence tests pass at `202609210001`. |
| MATRIX-22 - complete required scenario matrix | Coverage | Exact live provider plus controlled browser | PARTIAL | 2026-09-24 | `develop@77c5d67` plus scoped live evidence; controlled subset remains at `66008da15ea4ea23a5b1e99090441438bb163fba` | [current continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [current browser evidence](../../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [controlled module: 10 passed](../../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log), [original matrix report](../../QA/native-agent-loop-evaluation-20260917-final/final-report.md) | Location and coverage guardrail scenarios pass; inventory is partial at the model-call limit. Broad route, multilingual, composition, recovery, and Tier 2-5 rows remain open. |
| HOSTED-CI - exact implementation head | Hosted CI | GitHub Actions push workflow on `develop` | PASS | 2026-09-24 | `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` | [GitHub Actions run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085), [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | All four jobs passed: backend units/static analysis/OpenAPI, persistence conformance, capability contracts, and frontend build/unit tests/geospatial browser smoke. Runner/action migration notices were informational. |
| PROCESS-CLEANUP - task-owned services and browser | Test harness | Local host, ports 4512/7059/9876 | PASS | 2026-09-24 | `develop@77c5d67` plus scoped validation | [continuation report](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Task-owned backend/frontend processes were stopped and the three ports were free. The user-owned Chrome tab was left open; the configured isolated runtime was retained to preserve the user-saved provider configuration. |

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
