# Native Agent Validation Gate Ledger

Last updated: 2026-09-23 (T1-06 passed locally; corrected exact-head hosted CI pending)

This is the canonical current-status source for the native-agent loop,
geospatial routing, durable map presentation, browser recovery harness,
provider lane, migrations, and hosted-CI boundary. Status values are limited
to `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, and `UNRUN`.

Latest live-browser diary checkout: `77bf7e999a58a53fd6fbe99bee5c01b5d96060dc` on `loop-dev` (working tree; not committed or pushed).
Historical final tested repository head: `a33642a29c4353a760aac34bf1234b8121211da6` on `develop`.
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
| Tier 0 | Environment, schema, current-HEAD reconciliation | 5 | `PASS` | [Current Tier 0 reconciliation](../../QA/tier0-validation-develop-20260922/final/report.md): `T0-01` through `T0-05` are `PASS` on the same source boundary. |
| Tier 1 | Application foundations | 12 | `PARTIAL` | [Tier 1 checklist](tier1_application_foundations.md), [T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md), and [T1-02 continuation](../../QA/tier1-validation-develop-20260922/T1-02/report.md); 9 `PASS`, 3 `PARTIAL`. The 2026-09-21 [baseline ledger](../../QA/tier1-application-foundations-20260921/ledger.md) remains historical. |
| Tier 2 | Core agent workflows | 7 | `UNRUN` | Preserve exact-location and no-fallback boundaries. |
| Tier 3 | Rendering and geospatial feature families | 18 | `UNRUN` | Require browser-authoritative source/layer/render-ack evidence. |
| Tier 4A | Ingestion, local sources, optional integrations | 8 | `UNRUN` | Use isolated data and approved credentials/snapshots. |
| Tier 4B | Model-provider parity | 5 | `UNRUN` | Never substitute provider or model. |
| Tier 5 | Recovery, races, difficult boundaries, hosted CI | 13 | `UNRUN` | Open only after lower-tier contracts are classified. |

Campaign-slice status is 14 `PASS`, 3 `PARTIAL`, and 51 `UNRUN` of 68 slices.
These are the latest per-slice classifications across their linked source
boundaries, not a common-commit campaign result. Tier 1 remains `PARTIAL`; the
next actionable campaign slice is `T1-07`.
Hosted CI is a separate exact-head gate. The push run for
`fccafa1f48be71a8f68116b83783b29369e9e419` failed because the backend test
command referenced a missing test path. This continuation removes that stale
target; the corrected backend selection passes locally (397 tests). The
hosted-CI result for this continuation's exact pushed head remains separate and
is recorded in its [T1-06 hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-06/hosted-ci.md).

Tier 1 is not promoted to complete: `T1-07`, `T1-09`, and `T1-10` remain
partial. Keep their gaps visible in the
[Tier 1 checklist](tier1_application_foundations.md) and its linked reports.

## Current ledger

### Current Tier 0 slice ledger

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence |
| --- | --- | --- | --- | --- | --- |
| `T0-01` | Static quality | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-02` | Current SQLite migration/schema | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-03` | Legacy Settings migration | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-03 report](../../QA/tier0-validation-develop-20260922/T0-03/report.md) |
| `T0-04` | Windows startup | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-04 report](../../QA/tier0-validation-develop-20260922/T0-04/report.md) |
| `T0-05` | API composition and contract | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-05 report](../../QA/tier0-validation-develop-20260922/T0-05/report.md) |

Tier 0 is `PASS`. The overall campaign remains `PARTIAL` because three Tier 1
slices and the downstream live/browser/provider/hosted-CI boundaries remain
partial or unrun.

### Current Tier 1 continuation ledger

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `T1-02` | Frontend tab-local state | `PASS` | 2026-09-22 | `develop@8375fe071823e7f844f6bb125d86d6ebf36b3110` plus the source hashes recorded in the report; those source changes were later committed at `35d04f8399d0166d1a134ad9f45931bc15efda91` | [T1-02 report](../../QA/tier1-validation-develop-20260922/T1-02/report.md), [slice manifest](../../QA/tier1-validation-develop-20260922/T1-02/slice.json), [restored map controls screenshot](<../../QA/tier1-validation-develop-20260922/T1-02/screenshots/__test_refresh_same_tab_restores_chat_and_map_state[chromium]/t1-02-restored-map-state.png>) | Preserve its original test boundary; T1-03 is now passed. |
| `T1-03` | Conversation lifecycle and history | `PASS` | 2026-09-23 | `develop@35d04f8399d0166d1a134ad9f45931bc15efda91` plus the transcript CSS source hash recorded in the report | [T1-03 report](../../QA/tier1-validation-develop-20260923/T1-03/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-03/slice.json), [browser observations](../../QA/tier1-validation-develop-20260923/T1-03/browser-evidence.md) | Continue with `T1-07`; T1-06 has since passed. |
| `T1-06` | Synchronous `/api/chat/turn` contract | `PASS` | 2026-09-23 | `develop@4b5a6284379fd6f7fdcb2e523b2bde78e0387d87` plus the source fingerprints in the report; implementation commit recorded after push | [T1-06 report](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [slice manifest](../../QA/tier1-validation-develop-20260923/T1-06/slice.json), [redacted live HTTP matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json) | Continue with `T1-07`; keep hosted CI as an independent exact-head gate. |

| Gate ID / name | Subsystem | Lane / environment | Status | Verification date | Tested commit | Evidence link | Next action / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROUTE-UNIT — semantic catalog and alias contracts | Routing / catalog | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Preserve semantic subject matching, required aliases, generic-infrastructure clarification, and source-availability gates. |
| ROUTE-LIVE — exact-lane route matrix | Routing / catalog | Chrome UI, exact `opencode-go / deepseek-v4.1-flash` | PARTIAL | 2026-09-17 | `558f1966` | [manual-live-observations.md](../../QA/native-agent-loop-evaluation-20260917-final/manual-live-observations.md) | Repair and rerun Acropolis landmark-only semantics, imagery extent matching, weather execution budget, USGS/land-cover aliases, and generic infrastructure clarification. |
| STATE-V2 — ConversationState and clarification projection | Agent state | Local focused native pytest plus isolated API checks | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep schema version 2 and `pending_clarification` as the sole durable/public contract; accept `unresolved_questions` only as migration input. |
| PRESENTATION-TERMINAL — terminal run finalization | Run persistence | Local backend unit/native tests | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Preserve atomic closure for failed, cancelled, superseded, and timed-out runs with no pending presentation row. |
| FINALIZATION-OBS — sanitized tools-disabled traces | Trace observability | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep reason, model call index, `tools_exposed=0`, and `tool_choice=none`; never persist private reasoning, credentials, or raw provider payloads. |
| RENDER-ADMISSION — renderer-safe map candidates | Execution / render | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Continue requiring usable vector/raster/GeoJSON descriptors before candidate admission. |
| CONTROLLED-HAPPY — visible MapLibre completion | Browser / MapLibre | Local Angular + backend, WebSocket fixture after real browser ack | PASS | 2026-09-17 | `bf5a7cfa` | [controlled completion report](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-bf5-warm-final/reports/controlled-map-completion.json) | Preserve real `map.render_ack` gating and visible completion; this is controlled evidence only. |
| CONTROLLED-FAULT — recovery and acknowledgement matrix | Browser / MapLibre | Local controlled fixture; six fault cases pass, supersession case fails | PARTIAL | 2026-09-17 | `bf5a7cfa` | [controlled-browser-bf5-warm-final.log](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-bf5-warm-final.log) and [superseded report](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-bf5-warm-final/reports/controlled-map-superseded.json) | Fix the late superseded rejection ordering, then rerun the entire controlled module. |
| PROVIDER-READY — exact configured lane readiness | Provider | `opencode-go / deepseek-v4.1-flash`, `openai-chat-completions` | PASS | 2026-09-17 | `558f1966` | [final structured probe](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final/http/CHAT-LIVE-01/provider-structured-probe.json) | Preserve this exact lane; no fallback is permitted. |
| LIVE-BROWSER-SMOKE — realtime UI smoke | Browser / realtime | Local services 4512/7059, exact provider lane, isolated runtime data | PASS | 2026-09-17 | `558f1966` | [live-browser-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final.log) | Four tests passed: three exact-lane UI flows plus one intentional degraded-path stub; do not promote this subset to complete 22-scenario proof. |
| LIVE-DIARY-20260919 — representative geospatial browser diary | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, real chat workflow | PARTIAL | 2026-09-19 | `77bf7e9` + working tree | [validation diary](../../QA/aegis-geospatial-e2e-validation-20260919/report.md) | Rome-to-Florence recovery is browser-verified after the surgical loop fix; coordinate reverse geocoding, landmark/catalog coverage, provider availability, and the complete scenario matrix remain open. |
| LIVE-HYD-20260920 — hazard and hydrology rerun | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, live public providers | PARTIAL | 2026-09-20 | `84c210f6` | [hazard/hydrology rerun](../../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | FEMA raster retrieval is corrected but live MapLibre source loading still fails; GEO-HYD-05 and GEO-HYD-06 remain BLOCKED, and the current Zurich guardrail rerun is inconclusive. Keep the complete matrix PARTIAL. |
| LIVE-API — orchestration and ambiguity smoke | API orchestration | Exact provider lane, isolated runtime | PARTIAL | 2026-09-17 | `558f1966` | [api-live-final.log](../../QA/native-agent-loop-evaluation-20260917-final/api-live-final.log) | Investigate the typed 409 while `/api/chat/turn` is still running; keep the Ollama-unavailable 502 as a separate non-fallback boundary. |
| SYNC-CHAT-TURN — terminal hydration response | Backend API | Exact `opencode-go / deepseek-v4.1-flash` lane, isolated runtime, and focused API/OpenAPI pytest | PASS | 2026-09-23 | `develop@4b5a6284 + source hashes` | [T1-06 report](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [live HTTP matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json) | Preserve terminal hydration, genuine-conflict, accepted-run details, preflight, and safe provider-error behavior; retain hosted CI as an independent gate. |
| BACKEND-UNIT — full unit suite | Backend | `app/server/.venv`, isolated basetemp | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Retain the 832-test result and rerun when backend sources change. |
| NATIVE-FOCUSED — remediation regression suite | Backend / agent loop | `app/server/.venv`, isolated basetemp | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Retain the focused boundary for every future route, render, state, or finalization change. |
| RUFF — Python lint | Python quality | Repository-wide project-configured gate | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Ruff passes; keep protected-cache warnings separate from the lint result. |
| PYRIGHT-STRICT — repository strict typing | Static typing | `app/server/pyproject.toml` strict run | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Full repository run reports 0 errors, 0 warnings, and 0 informations; rerun after typing or project-configuration changes. |
| FRONTEND-BUILD — production bundle | Angular client | Local `npm run build` | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Keep generated `dist` output out of source control. |
| FRONTEND-KARMA — client regression suite | Angular client | ChromeHeadlessNoGpu | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | 248/248 pass; add browser-timing coverage before retrying supersession remediation. |
| MIGRATION — isolated upgrade/head/check | Persistence schema | Isolated SQLite under dated QA data | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Fresh upgrade, `alembic check`, `current --check-heads`, and 25 migration/persistence tests pass at `202609210001`. |
| MATRIX-22 — complete required scenario matrix | Coverage | Exact live provider plus controlled browser | PARTIAL | 2026-09-17 | `bf5a7cfa` | [final-report.md](../../QA/native-agent-loop-evaluation-20260917-final/final-report.md) | Complete the explicit PARTIAL and UNRUN rows, including a separate mismatched-ack case, before any overall PASS claim. |
| HOSTED-CI — exact tested head | Hosted CI | GitHub Actions push workflow on `develop`; corrected backend job passes locally | PARTIAL | 2026-09-23 | `4b5a6284 + T1-06 source changes` | [T1-06 hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-06/hosted-ci.md), [previous failed run](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35834459171) | The stale test target is removed and the corrected 397-test backend selection passes locally; inspect the exact pushed head and retain PARTIAL until hosted CI passes. |
| PROCESS-CLEANUP — task-owned services and browser | Test harness | Local host, ports 4512/7059/9876 | PASS | 2026-09-22 | `7e8b10d5 + WT` | [T0-04 report](../../QA/tier0-validation-develop-20260922/T0-04/report.md) | Final harness services stopped; ports verified free; unrelated processes survived readiness-failure cleanup. |

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
