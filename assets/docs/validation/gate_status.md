# Native Agent Validation Gate Ledger

Last updated: 2026-09-23 (current-head T2 retry: T2-01/02 PARTIAL, T2-03 PASS; LIVE-API recheck PASS)

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
| Tier 1 | Application foundations | 12 | `PASS` | [Tier 1 checklist](tier1_application_foundations.md), [T1-10 continuation](../../QA/tier1-validation-develop-20260923/T1-10/report.md), [T1-09 continuation](../../QA/tier1-validation-develop-20260923/T1-09/report.md), [T1-07 continuation](../../QA/tier1-validation-develop-20260923/T1-07/report.md), [T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md), and [T1-02 continuation](../../QA/tier1-validation-develop-20260922/T1-02/report.md); 12 `PASS`. The 2026-09-21 [baseline ledger](../../QA/tier1-application-foundations-20260921/ledger.md) remains historical. |
| Tier 2 | Core agent workflows | 7 | `PARTIAL` | [Current T2 retry](../../QA/tier2-validation-develop-20260923-retry/report.md): `T2-01`/`T2-02` are `PARTIAL`, `T2-03` is `PASS`, and `T2-04`–`T2-07` remain `UNRUN`. |
| Tier 3 | Rendering and geospatial feature families | 18 | `UNRUN` | Require browser-authoritative source/layer/render-ack evidence. |
| Tier 4A | Ingestion, local sources, optional integrations | 8 | `UNRUN` | Use isolated data and approved credentials/snapshots. |
| Tier 4B | Model-provider parity | 5 | `UNRUN` | Never substitute provider or model. |
| Tier 5 | Recovery, races, difficult boundaries, hosted CI | 13 | `UNRUN` | Open only after lower-tier contracts are classified. |

Campaign-slice status is 18 `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 48 `UNRUN`
of 68 slices. These are the latest per-slice classifications across their
linked source boundaries, not a common-commit campaign result. Tier 1 is
`PASS`; Tier 2 remains `PARTIAL` with Milan disambiguation and Florence
confirmation limitations, while T2-04 through T2-07 remain unrun. The latest
current-head retry and its source fixes are documented in the
[T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md).
Hosted CI is a separate exact-head gate. The earlier push run for
`fccafa1f48be71a8f68116b83783b29369e9e419` failed because its backend test
command referenced a missing path. The corrected implementation commit
`af663adaa5e14be3fcd7312e4bd230cca11f1b40` passed all four jobs on
[run 35845587545](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35845587545);
see the [T1-06 hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-06/hosted-ci.md).
The T1-07 implementation commit
`3fd0c820c2d4de0fb06120b6feac80b199d57f26` is pushed to `develop`; its
exact-head [CI run 35861096479](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35861096479)
passed all four jobs; see the
[T1-07 hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-07/hosted-ci.md).
The T1-09 implementation commit
`c090abd1ca9d6d78e82e798da9167b9d19b3fc23` is pushed to `develop`; its
exact-head [CI run 35873578752](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35873578752)
passed all four jobs; see the
[T1-09 hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-09/hosted-ci.md).
The T1-10 implementation commit
`8e32f82e3f094e5fb17c3978fad69b9f80b7af0b` is pushed to `develop`; its exact-head
[CI run 35891289442](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35891289442)
passed all four jobs; see the
[T1-10 hosted-CI record](../../QA/tier1-validation-develop-20260923/T1-10/hosted-ci.md).

The local T1-10 credential slice passed on
`develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; its exact pushed-head CI
passed all four jobs. Tier 1 is complete at 12 `PASS`; continue with `T2-01`
while preserving the downstream `PARTIAL`, `BLOCKED`, and `UNRUN` gates below.
The current T2 retry records T2-03 as `PASS`, T2-01/02 as `PARTIAL`, and
T2-04 through T2-07 as `UNRUN`; see the
[T2 validation retry](../../QA/tier2-validation-develop-20260923-retry/report.md).

## Current ledger

### Current Tier 0 slice ledger

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence |
| --- | --- | --- | --- | --- | --- |
| `T0-01` | Static quality | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-02` | Current SQLite migration/schema | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) |
| `T0-03` | Legacy Settings migration | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-03 report](../../QA/tier0-validation-develop-20260922/T0-03/report.md) |
| `T0-04` | Windows startup | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-04 report](../../QA/tier0-validation-develop-20260922/T0-04/report.md) |
| `T0-05` | API composition and contract | `PASS` | 2026-09-22 | `develop@afa608c8d5c53a34d0ce8da36e5fe5f47f689145` | [T0-05 report](../../QA/tier0-validation-develop-20260922/T0-05/report.md) |

Tier 0 and Tier 1 are `PASS`. The overall campaign remains `PARTIAL`: Tier 2
contains two `PARTIAL`, one `PASS`, and four `UNRUN` slices, Tier 3–5 remain
`UNRUN`, and downstream live/browser/provider boundaries remain partial or
blocked. The current T2 retry and source changes are pushed and recorded below;
hosted CI is tracked against the exact pushed validation head.

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

The latest retry used application sources at
`develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371`. The official launcher
reached backend and frontend health with an isolated runtime; the exact provider
lane was visible and reached `Verified`. The earlier launcher-timeout attempt
remains historical evidence in the original report.

| Slice | Scope | Status | Verification date | Tested source boundary | Evidence | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `T2-01` | Plain and ambiguous locations; Springfield clarification; invalid-coordinate retention; Italian-context Milan request | `PARTIAL` | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), historical [core browser report](../../QA/core-behavior-e2e-20260919/final-report.md) | Keep `Mostrami Milano` clarification visible and improve/revalidate the Texas alternative and `Rodano` label; Zurich bounds rejection and Springfield clarification/render passed. |
| `T2-02` | Hydrated Rome to ambiguous Florence, then explicit Florence, Tuscany, Italy replacement | `PARTIAL` | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), historical [2026-09-19 diary](../../QA/aegis-geospatial-e2e-validation-20260919/report.md) | Hydration and explicit Florence render passed; clarify before replacing Rome when the location remains ambiguous, then rerun the full transition. |
| `T2-03` | Landmark and point-of-interest routing | `PASS` | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md) | Colosseum and clarified central-Rome POI flows resolved, retrieved, rendered, and acknowledged; preserve the partial-reliability and roughly 2.5 km Overpass coverage note. |
| `T2-04` | Capability discovery | `UNRUN` | — | — | [Validation strategy](strategy.md) | Validate only after current location slices have browser-authoritative evidence. |
| `T2-05` | Direct tools | `UNRUN` | — | — | [Validation strategy](strategy.md) | Validate tool routing, result semantics, and any requested rendered map. |
| `T2-06` | Conversation history | `UNRUN` | — | — | [Validation strategy](strategy.md) | Validate hydrated state and replay behavior with visible browser evidence. |
| `T2-07` | Evidence inspection | `UNRUN` | — | — | [Validation strategy](strategy.md) | Validate evidence provenance and matching render acknowledgement. |

| Gate ID / name | Subsystem | Lane / environment | Status | Verification date | Tested commit | Evidence link | Next action / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROUTE-UNIT — semantic catalog and alias contracts | Routing / catalog | Local focused native pytest | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current focused checks](../../QA/tier2-validation-develop-20260923-retry/report.md), [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Current POI route regression passes; preserve semantic subject matching, required aliases, generic-infrastructure clarification, and source-availability gates. |
| ROUTE-LIVE — exact-lane route matrix | Routing / catalog | Chrome UI, exact `opencode-go / deepseek-v4.1-flash` | PARTIAL | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current T2 retry](../../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), [historical route observations](../../QA/native-agent-loop-evaluation-20260917-final/manual-live-observations.md) | T2-03 Rome/Colosseum POI routing passes after adding data and render route domains. The broad matrix remains partial for Acropolis landmark-only semantics, imagery extent matching, weather execution budget, USGS/land-cover aliases, generic-infrastructure clarification, and Milan candidate quality. |
| STATE-V2 — ConversationState and clarification projection | Agent state | Local focused native pytest plus isolated API checks | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep schema version 2 and `pending_clarification` as the sole durable/public contract; accept `unresolved_questions` only as migration input. |
| PRESENTATION-TERMINAL — terminal run finalization | Run persistence | Local backend unit/native tests | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Preserve atomic closure for failed, cancelled, superseded, and timed-out runs with no pending presentation row. |
| FINALIZATION-OBS — sanitized tools-disabled traces | Trace observability | Local focused native pytest | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current focused checks](../../QA/tier2-validation-develop-20260923-retry/report.md), [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Raw DSML finalization content is suppressed; keep reason, model call index, `tools_exposed=0`, and `tool_choice=none`; never persist private reasoning, credentials, or raw provider payloads. |
| RENDER-ADMISSION — renderer-safe map candidates | Execution / render | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Continue requiring usable vector/raster/GeoJSON descriptors before candidate admission. |
| CONTROLLED-HAPPY — visible MapLibre completion | Browser / MapLibre | Local Angular + backend, WebSocket fixture after real browser ack | PASS | 2026-09-17 | `bf5a7cfa` | [controlled completion report](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-bf5-warm-final/reports/controlled-map-completion.json) | Preserve real `map.render_ack` gating and visible completion; this is controlled evidence only. |
| CONTROLLED-FAULT — recovery and acknowledgement matrix | Browser / MapLibre | Local controlled fixture; six fault cases pass, supersession case fails | PARTIAL | 2026-09-17 | `bf5a7cfa` | [controlled-browser-bf5-warm-final.log](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-bf5-warm-final.log) and [superseded report](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-bf5-warm-final/reports/controlled-map-superseded.json) | Fix the late superseded rejection ordering, then rerun the entire controlled module. |
| PROVIDER-READY — exact configured lane readiness | Provider | `opencode-go / deepseek-v4.1-flash`, `openai-chat-completions` | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current exact-lane browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), [final structured probe](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final/http/CHAT-LIVE-01/provider-structured-probe.json) | Preserve this exact lane; no fallback is permitted. |
| LIVE-BROWSER-SMOKE — realtime UI smoke | Browser / realtime | Local services 4512/7059, exact provider lane, isolated runtime data | PASS | 2026-09-17 | `558f1966` | [live-browser-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final.log) | Four tests passed: three exact-lane UI flows plus one intentional degraded-path stub; do not promote this subset to complete 22-scenario proof. |
| LIVE-DIARY-20260919 — representative geospatial browser diary | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, real chat workflow | PARTIAL | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current T2 retry](../../QA/tier2-validation-develop-20260923-retry/report.md), [current browser evidence](../../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), [historical validation diary](../../QA/aegis-geospatial-e2e-validation-20260919/report.md) | Rome hydration, explicit Florence, and plain-location browser runs now pass, while ambiguous Florence still changes the map without confirmation. Coordinate reverse geocoding, other landmark/catalog paths, provider availability, and the full scenario matrix remain open. |
| LIVE-HYD-20260920 — hazard and hydrology rerun | Browser / realtime / MapLibre | Local services 4512/7059, exact `opencode-go / deepseek-v4.1-flash`, live public providers | PARTIAL | 2026-09-20 | `84c210f6` | [hazard/hydrology rerun](../../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | FEMA raster retrieval is corrected but live MapLibre source loading still fails; GEO-HYD-05 and GEO-HYD-06 remain BLOCKED, and the current Zurich guardrail rerun is inconclusive. Keep the complete matrix PARTIAL. |
| LIVE-API — orchestration and ambiguity smoke | API orchestration | Exact provider lane, isolated runtime | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current live API recheck](../../QA/tier2-validation-develop-20260923-retry/live-api-recheck.json), [T1-06 historical live matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json), [historical API log](../../QA/native-agent-loop-evaluation-20260917-final/api-live-final.log) | Current exact-lane recheck returned 200 then 409 for a concurrent same-conversation request, with one terminal persisted run and isolated DB integrity `ok`. Keep the Ollama-unavailable `502` as a separate non-fallback boundary. |
| SYNC-CHAT-TURN — terminal hydration response | Backend API | Exact `opencode-go / deepseek-v4.1-flash` lane, isolated runtime, and focused API/OpenAPI pytest | PASS | 2026-09-23 | `develop@af663adaa5e14be3fcd7312e4bd230cca11f1b40` | [T1-06 report](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [live HTTP matrix](../../QA/tier1-validation-develop-20260923/T1-06/live-http-matrix.json) | Preserve terminal hydration, genuine-conflict, accepted-run details, preflight, and safe provider-error behavior. |
| BACKEND-UNIT — full unit suite | Backend | Standard Windows test runner, isolated basetemp | PASS | 2026-09-23 | `develop@3fd0c820c2d4de0fb06120b6feac80b199d57f26` | [T1-07 report](../../QA/tier1-validation-develop-20260923/T1-07/report.md), [full unit log](../../QA/tier1-validation-develop-20260923/T1-07/backend-unit.log) | 918 tests pass, including app-lifespan cleanup and all job lifecycle/API tests. |
| NATIVE-FOCUSED — remediation regression suite | Backend / agent loop | `app/server/.venv`, isolated basetemp | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current focused checks](../../QA/tier2-validation-develop-20260923-retry/report.md), [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | 86 route, location, and finalization tests pass; retain the focused boundary for every future route, render, state, or finalization change. |
| RUFF — Python lint | Python quality | Six changed agent/source test files | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [current focused checks](../../QA/tier2-validation-develop-20260923-retry/report.md), [T1-07 report](../../QA/tier1-validation-develop-20260923/T1-07/report.md) | All checks pass; the prior full-repository result remains in the T1-07 report. |
| PYRIGHT-STRICT — repository strict typing | Static typing | `app/server/pyproject.toml` strict run | PASS | 2026-09-23 | `develop@3fd0c820c2d4de0fb06120b6feac80b199d57f26` | [T1-07 report](../../QA/tier1-validation-develop-20260923/T1-07/report.md), [Pyright log](../../QA/tier1-validation-develop-20260923/T1-07/pyright.log) | Full repository run reports 0 errors, 0 warnings, and 0 informations. |
| FRONTEND-BUILD — production bundle | Angular client | Local `npm run build` via official launcher | PASS | 2026-09-23 | `develop@155e1e22ce34a4b2698f474afa60b57f61b56916` | [T2 validation report](../../QA/tier2-validation-develop-20260923/report.md) | The production bundle completed; backend readiness still blocked live browser validation. Keep generated `dist` output out of source control. |
| FRONTEND-KARMA — client regression suite | Angular client | ChromeHeadlessNoGpu | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | 248/248 pass; add browser-timing coverage before retrying supersession remediation. |
| MIGRATION — isolated upgrade/head/check | Persistence schema | Isolated SQLite under dated QA data | PASS | 2026-09-22 | `7e8b10d5 + WT` | [Tier 0 final report](../../QA/tier0-validation-develop-20260922/final/report.md) | Fresh upgrade, `alembic check`, `current --check-heads`, and 25 migration/persistence tests pass at `202609210001`. |
| MATRIX-22 — complete required scenario matrix | Coverage | Exact live provider plus controlled browser | PARTIAL | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [original matrix report](../../QA/native-agent-loop-evaluation-20260917-final/final-report.md) | T2-01/02/03 and the live API conflict row now have current evidence; complete all remaining PARTIAL/UNRUN rows, including a separate mismatched-ack case, before an overall PASS claim. |
| HOSTED-CI — exact tested head | Hosted CI | GitHub Actions push workflow on `develop` | PASS | 2026-09-23 | `develop@53260863c2f0fa9b1ffc5b64e9edc687236eb91d` | [exact-head GitHub Actions run 35901790479](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35901790479), [T2 validation report](../../QA/tier2-validation-develop-20260923/report.md) | All four jobs passed on the pushed validation commit; current live-browser slices remain `BLOCKED` as reported.
| PROCESS-CLEANUP — task-owned services and browser | Test harness | Local host, ports 4512/7059/9876 | PASS | 2026-09-23 | `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371` | [T2 retry report](../../QA/tier2-validation-develop-20260923-retry/report.md), [isolated launcher log](../../QA/tier2-validation-develop-20260923-retry/official-launcher-route-fix.log) | Exact launcher-owned backend/frontend processes were stopped; ports were free and `.env` was restored byte-for-byte. |

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
