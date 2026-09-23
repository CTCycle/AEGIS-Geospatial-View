# Tier 2 and live API validation retry

- Date: 2026-09-23
- Branch/source boundary: `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371`
- Starting source: `2a2fa45aecd8840c58b96a863c47e6bedfd989fc`
- Launcher: official Windows launcher, `start_on_windows.ps1 -Action Launch`
- Exact provider/model lane: `opencode-go / deepseek-v4.1-flash`; no fallback.
- Detailed rendered observations: [browser evidence](browser-evidence.md).

## Selected scope and results

The current ledger showed `T2-01` and `T2-02` blocked before browser validation, `T2-03` unrun with `ISSUE-001` open, and the `LIVE-API` active-run conflict recheck blocked. These form a manageable location/map and adjacent API recheck. The final statuses are:

| Item | Final status | Evidence and limitation |
| --- | --- | --- |
| `T2-01` | `PARTIAL` | Zurich bounds rejection and Springfield clarification/render passed. Milan rendered after selection, but the clarification still offers an incongruous Texas candidate and a `Rodano` label. |
| `T2-02` | `PARTIAL` | Rome hydration and explicit Florence render passed; an unqualified Florence follow-up still replaces Rome without asking for confirmation. DSML protocol text is suppressed. |
| `T2-03` | `PASS` | Colosseum and central Rome location-to-POI-to-visible-map flows passed. The provider labels its reliability partial and returned a roughly 2.5 km extent. |
| `LIVE-API` | `PASS` | Current-head live request returned HTTP 200; a concurrent request returned HTTP 409 `Conversation already has an active run.` Exactly one terminal run persisted; isolated database integrity check was `ok`. See [live API result](live-api-recheck.json). |

Tier 2 remains `PARTIAL`: one pass, two partial slices, and four unrun slices (`T2-04` through `T2-07`). The campaign roll-up becomes 18 `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 48 `UNRUN` of 68 slices. Tier 0 and Tier 1 remain `PASS`; Tier 3, Tier 4A, Tier 4B, and Tier 5 remain `UNRUN`.

## Implementation changes

- Location matching now checks an explicit country qualifier against the geocoder candidate's country and ISO code. This rejects the Tehran/Iran candidate for `central Rome, Italy` while accepting Rome/Italy.
- POI map requests routed through `PLACE_SEARCH` now receive both `MAP_RENDERING` and `DATA_RETRIEVAL`, including when the classifier omits secondary domains. Live trace evidence exposed the previous route rejection; the repaired pharmacy and central-Rome flows completed.
- Tools-disabled finalization suppresses raw DSML protocol-looking content and uses the safe render acknowledgement. The Florence follow-up did not expose protocol text.

## Local checks

Focused backend tests, run with the repository's isolated pytest paths:

```powershell
app/server/.venv/Scripts/python.exe -m pytest -c app/server/pyproject.toml --basetemp=runtimes/cache/pytest-tmp/t2-recheck-20260923 app/tests/unit/services/agent/test_capability_router.py app/tests/unit/services/agent/test_location_resolver.py app/tests/unit/services/agent/test_agent_loop_v2.py
```

Result: `86 passed in 0.52s`.

Ruff on the six changed Python source/test files reported `All checks passed!`; `git diff --check` reported no whitespace errors. The official launcher returned HTTP 200 for frontend and backend readiness. `.env` was temporarily pointed at the isolated runtime and restored byte-for-byte after startup.

## Other current gate boundaries

- `ROUTE-LIVE` and `LIVE-DIARY` remain `PARTIAL`: this campaign closes the Rome/Colosseum POI issue and adds location/hydration evidence, but does not cover Acropolis landmark-only semantics, imagery extent matching, weather execution budgets, USGS/land-cover aliases, generic-infrastructure clarification, coordinate reverse geocoding, or the complete diary matrix. Milan remains an attention item.
- `LIVE-HYD` remains `PARTIAL`; FEMA/ESA source loading and dependent composition remain unresolved, and the Zurich coverage-guardrail rerun is inconclusive.
- `CONTROLLED-FAULT` remains `PARTIAL` because late superseded acknowledgement ordering still fails. `MATRIX-22` and `testing.complete-live-matrix` remain `PARTIAL` because other explicit `PARTIAL`/`UNRUN` cases, including mismatched-ack evidence, remain.
- `T2-04` capability-discovery breadth, `T2-05` direct tools, `T2-06` history/replay breadth, and `T2-07` evidence-inspection breadth remain `UNRUN`; the hydration check in `T2-02` does not substitute for those wider gates.
- Provider parity and credentialed/local-source access remain `BLOCKED`; dataset ingestion remains unvalidated. No evidence in this campaign changes those boundaries.

## Data isolation and cleanup

An initial launcher invocation ignored process-level `AEGIS_DATA_DIR` overrides and loaded the repository's canonical database. Seven task-generated test conversations were identified by exact ID/title, confirmed terminal, and deleted with their dependent test rows. The cleanup removed seven conversations, 14 runs, 28 messages, 495 run events, and two evidence rows; the canonical database returned to its pre-test count of 328 conversations, with `foreign_key_check` empty and `integrity_check=ok`. No other conversation rows were changed.

The final browser and API runs used the isolated test runtime. The isolated API list contained its five fixture conversations, and the canonical-probe conversation was absent. After testing, the exact launcher-owned backend/frontend processes were stopped, ports 4512/7059/9876 were checked free, and the task-owned isolated runtime and pytest temp directory were removed. The original `settings/.env` bytes were restored and compared byte-for-byte.

The seven removed task-generated IDs were:

- `conv_c51979ee8d0a49fcb183469b48232bcf`
- `conv_286911a52c8845578aa5bd1aece0636a`
- `conv_06fe4152386941fda21657082e88975e`
- `conv_f03829c4d8b742a7ac5705f3d34d5d6f`
- `conv_c54020f78f66401794e166637b9c6355`
- `conv_04db0b71693f4fc499f4bda72e3ce5cd`
- `conv_3ccaf0e3a3cc417e9996153b4e23760d`

## Hosted CI

Hosted CI for the pushed source-and-evidence head is recorded in the current validation gate ledger after the exact-head workflow completes.
