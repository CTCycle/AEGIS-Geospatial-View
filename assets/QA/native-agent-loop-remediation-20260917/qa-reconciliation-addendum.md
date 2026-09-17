# QA reconciliation addendum

Date: 2026-09-17
Repository: AEGIS Geospatial View
Branch: `develop`
Verified revision: `05e5046d9a0f79d615ad7187cf3d5c4aea085b06`

This addendum records the final local verification snapshot after the
incremental remediation commits. The dated evaluation files and the original
`final-report.md` remain immutable historical evidence; this file reconciles
their status with the current checkout.

## Incremental implementation series

The current remediation series is:

1. `72ff51b1` — align capability routing with catalog contracts.
2. `dd868a33` — enforce render-safe recovery and correction.
3. `50558f9c` — complete native-loop observability and gate tracking.
4. `3d455feb` — normalize native gate statuses.
5. `758c7fbd` — type bounded correction payloads.
6. `2633923a` — type clarification migration paths.
7. `772ed3b8` — record final validation gate results.
8. `675ac9f1` — emit explicit finalization trace events.
9. `ab357734` — preserve the first render failure cause.
10. `8b3f2d99` — clarify broad infrastructure routing.
11. `a4054302` — align migration head and shared OpenAPI contract.
12. `05e5046d` — make pending clarification the sole state contract.

## Current local verification

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Full backend unit suite | PASS | `pytest app/tests/unit -q`: **809 passed, 3 warnings** at the verified revision. Warnings are dependency deprecations and a protected pytest-cache write warning. |
| Native remediation integration slice | PASS | Focused native/routing/render/state/migration slice: **129 passed, 3 warnings** at the verified revision. |
| Ruff | PASS | `app/server/.venv/Scripts/ruff.exe check --no-cache app/server app/tests`: all checks passed; protected-cache access warnings remain environmental. |
| Full strict Pyright | FAIL | `pyright --project app/server/pyproject.toml`: **47 errors**, all in the existing AgentLoop complexity/unused-variable cascade, provider Optional access, maintenance diagnostics typing, and transport checks. No new clarification/correction typing error was reported. |
| Angular production build | PASS | `npm run build` completed in 17.043 seconds; generated `app/client/dist` is ignored build output. |
| Angular Karma suite | PASS | `npm run test -- --watch=false --browsers=ChromeHeadlessNoGpu`: **228 tests succeeded**; only Angular deprecation, sanitizer, and 404 warnings were reported. |
| Controlled browser fault matrix | BLOCKED | The fixture collects **8 tests** (happy path plus failed-layer, viewport mismatch, stale/duplicate acknowledgement, cancellation, supersession, and retry exhaustion). Execution requires the canonical services; ports `8000` and `8001` were not listening. No browser PASS is inferred from collection. |
| Configured live provider | BLOCKED | The required `opencode-go / deepseek-v4.1-flash` lane was not available for post-remediation completion. No fallback provider or catalog reachability was promoted to live PASS. |
| Hosted CI at exact revision | UNRUN | No push or hosted run was requested. |

The evaluation report remains the source for the original native probe and
scenario evidence:

- [Original final report](final-report.md)
- [Scenario matrix](../native-agent-loop-evaluation-20260917/scenario-matrix.md)
- [Trace evidence](../native-agent-loop-evaluation-20260917/trace-evidence.md)
- [Controlled recovery results](../native-agent-loop-evaluation-20260917/controlled-recovery.md)
- [Browser evidence](../native-agent-loop-evaluation-20260917/browser-evidence.md)

No provider outage was established. Existing pytest-temp directories and other
unrelated worktree artifacts were preserved.
