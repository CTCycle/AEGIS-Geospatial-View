# Native Agent Validation Gate Ledger

Last updated: 2026-09-17 (final local evaluation)

This is the canonical current-status source for the native-agent loop,
geospatial routing, durable map presentation, browser recovery harness,
provider lane, migrations, and hosted-CI boundary. Status values are limited
to `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, and `UNRUN`.

Tested source commit for this evaluation: `558f1966afc3cef4b6e755d4edfdc87dfd258c11` on `develop`.

## Current ledger

| Gate ID / name | Subsystem | Lane / environment | Status | Verification date | Tested commit | Evidence link | Next action / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROUTE-UNIT — semantic catalog and alias contracts | Routing / catalog | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Preserve semantic subject matching, required aliases, generic-infrastructure clarification, and source-availability gates. |
| ROUTE-LIVE — exact-lane route matrix | Routing / catalog | Chrome UI, exact `opencode-go / deepseek-v4.1-flash` | PARTIAL | 2026-09-17 | `558f1966` | [manual-live-observations.md](../../QA/native-agent-loop-evaluation-20260917-final/manual-live-observations.md) | Repair and rerun Acropolis landmark-only semantics, imagery extent matching, weather execution budget, USGS/land-cover aliases, and generic infrastructure clarification. |
| STATE-V2 — ConversationState and clarification projection | Agent state | Local focused native pytest plus isolated API checks | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep schema version 2 and `pending_clarification` as the sole durable/public contract; accept `unresolved_questions` only as migration input. |
| PRESENTATION-TERMINAL — terminal run finalization | Run persistence | Local backend unit/native tests | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Preserve atomic closure for failed, cancelled, superseded, and timed-out runs with no pending presentation row. |
| FINALIZATION-OBS — sanitized tools-disabled traces | Trace observability | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Keep reason, model call index, `tools_exposed=0`, and `tool_choice=none`; never persist private reasoning, credentials, or raw provider payloads. |
| RENDER-ADMISSION — renderer-safe map candidates | Execution / render | Local focused native pytest | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Continue requiring usable vector/raster/GeoJSON descriptors before candidate admission. |
| CONTROLLED-HAPPY — visible MapLibre completion | Browser / MapLibre | Local Angular + backend, WebSocket fixture after real browser ack | PASS | 2026-09-17 | `558f1966` | [controlled completion report](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-558f-final/reports/controlled-map-completion.json) | Preserve real `map.render_ack` gating and visible completion; this is controlled evidence only. |
| CONTROLLED-FAULT — recovery and acknowledgement matrix | Browser / MapLibre | Local controlled fixture; six fault cases pass, supersession case fails | PARTIAL | 2026-09-17 | `558f1966` | [controlled-browser-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/controlled-browser-558f-final.log) | Fix the late superseded rejection ordering, then rerun the entire controlled module. |
| PROVIDER-READY — exact configured lane readiness | Provider | `opencode-go / deepseek-v4.1-flash`, `openai-chat-completions` | PASS | 2026-09-17 | `558f1966` | [final structured probe](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final/http/CHAT-LIVE-01/provider-structured-probe.json) | Preserve this exact lane; no fallback is permitted. |
| LIVE-BROWSER-SMOKE — realtime UI smoke | Browser / realtime | Local services 4512/7059, exact provider lane, isolated runtime data | PASS | 2026-09-17 | `558f1966` | [live-browser-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/live-browser-558f-final.log) | Four tests passed: three exact-lane UI flows plus one intentional degraded-path stub; do not promote this subset to complete 22-scenario proof. |
| LIVE-API — orchestration and ambiguity smoke | API orchestration | Exact provider lane, isolated runtime | PARTIAL | 2026-09-17 | `558f1966` | [api-live-final.log](../../QA/native-agent-loop-evaluation-20260917-final/api-live-final.log) | Investigate the typed 409 while `/api/chat/turn` is still running; keep the Ollama-unavailable 502 as a separate non-fallback boundary. |
| SYNC-CHAT-TURN — terminal hydration response | Backend API | Exact provider lane, isolated runtime | PARTIAL | 2026-09-17 | `558f1966` | [api-live-final.log](../../QA/native-agent-loop-evaluation-20260917-final/api-live-final.log) | Make the synchronous endpoint boundary explicit or await completion before returning; current 409 is not a generic catalog error. |
| BACKEND-UNIT — full unit suite | Backend | `app/server/.venv`, isolated basetemp | PASS | 2026-09-17 | `558f1966` | [backend-unit-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/backend-unit-final-commit.log) | Retain the 832-test result and rerun when backend sources change. |
| NATIVE-FOCUSED — remediation regression suite | Backend / agent loop | `app/server/.venv`, isolated basetemp | PASS | 2026-09-17 | `558f1966` | [focused-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/focused-final-commit.log) | Retain the focused boundary for every future route, render, state, or finalization change. |
| RUFF — Python lint | Python quality | Local no-cache run | PASS | 2026-09-17 | `558f1966` | [ruff-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/ruff-final-commit.log) | Keep protected-cache warnings separate from lint outcome. |
| PYRIGHT-STRICT — repository strict typing | Static typing | `app/server/pyproject.toml` strict run | FAIL | 2026-09-17 | `558f1966` | [pyright-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/pyright-final-commit.log) | Resolve the remaining 46 repository diagnostics and rerun. The repaired map descriptor diagnostics are no longer present. |
| FRONTEND-BUILD — production bundle | Angular client | Local `npm run build` | PASS | 2026-09-17 | `558f1966` | [frontend-build-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/frontend-build-558f-final.log) | Keep generated `dist` output out of source control. |
| FRONTEND-KARMA — client regression suite | Angular client | ChromeHeadlessNoGpu | PASS | 2026-09-17 | `558f1966` | [frontend-karma-558f-final.log](../../QA/native-agent-loop-evaluation-20260917-final/frontend-karma-558f-final.log) | 233/233 pass; add browser-timing coverage before retrying supersession remediation. |
| MIGRATION — isolated upgrade/head/check | Persistence schema | Isolated SQLite under dated QA data | PASS | 2026-09-17 | `558f1966` | [migration-final-commit.log](../../QA/native-agent-loop-evaluation-20260917-final/migration-final-commit.log) | Keep migration head `202609170001` and rerun only against isolated data. |
| MATRIX-22 — complete required scenario matrix | Coverage | Exact live provider plus controlled browser | PARTIAL | 2026-09-17 | `558f1966` | [final-report.md](../../QA/native-agent-loop-evaluation-20260917-final/final-report.md) | Complete the explicit PARTIAL and UNRUN rows, including a separate mismatched-ack case, before any overall PASS claim. |
| HOSTED-CI — exact tested head | Hosted CI | Remote workflow | BLOCKED | 2026-09-17 | `558f1966` | [evidence-index.md](../../QA/native-agent-loop-evaluation-20260917-final/evidence-index.md) | No push or CI ownership change was authorized; run only when an authorized hosted boundary exists. |
| PROCESS-CLEANUP — task-owned services and browser | Test harness | Local host, ports 4512/7059/9876 | PASS | 2026-09-17 | `558f1966` | [process-cleanup-final.md](../../QA/native-agent-loop-evaluation-20260917-final/process-cleanup-final.md) | Task-owned AEGIS services and browser tab stopped; unrelated services and caches preserved. |

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
