# Tier 2 live continuation and gate reconciliation

- Date: 2026-09-24
- Branch: `develop`
- Starting commit: `77c5d67afe1121801f3a86cc5953d3e0dcea667e`
Validation source: scoped implementation and test changes based on the starting commit, committed with this evidence.

Validation used the official Windows launcher and isolated runtime at `runtimes/cache/test-runtime/validation-20260924-exact-lane`. After the launcher restart, Settings showed the exact `opencode-go / deepseek-v4.1-flash` model selected; `Test selected model` returned `Verified` and `Native tool probe passed`. No alternate provider or model was used. The user-configured provider data remains in the isolated runtime and is not included in source control or evidence.

## Current results

| Gate or slice | Final status | Current evidence and remaining boundary |
| --- | --- | --- |
| `ROUTE-UNIT` | `PASS` | 155 focused routing, catalog, location, tool, agent-loop, and Nominatim tests pass. One existing pytest warning reports unknown `cache_dir`. See [`focused-backend-final.log`](focused-backend-final.log). |
| `RUFF` | `PASS` | Ruff passed for all modified agent, geospatial-service, and focused-test files. See [`ruff-final.log`](ruff-final.log). |
| `T2-01` | `PASS` | The initial live check exposed a verbose Milan candidate label; the resolver now uses structured locality/region/country fields. On the retest, `Mostrami Milano.` asked the user to choose between the clear options `Milano, Texas, United States` and `Milan, Lombardy, Italy`; explicit `Milano, Italia` then rendered and was acknowledged at Milan, Lombardy, Italy with OpenStreetMap attribution. Earlier Springfield clarification and invalid-coordinate retention evidence remains linked from the prior browser record. |
| `T2-02` | `PASS` | Rome rendered first; `Show me Florence.` then asked which Florence while Rome remained displayed; choosing Florence, Tuscany, Italy rendered and was acknowledged. Both maps showed OpenStreetMap attribution. |
| `T2-03` | `PASS` | Prior exact-lane Colosseum and Rome POI result/render/acknowledgement evidence remains current for its recorded source boundary. Overpass reliability and extent remain limited. |
| `T2-04` | `PARTIAL` | The no-map inventory request completed three `discover_geospatial_capabilities` pages of 12 each (36 candidates). The UI reported the configured execution limit at `max_model_calls=4`; the bounded catalog contains up to 50 candidates, so discovery did not complete. No map was requested or rendered. |
| `FEMA-COVERAGE-GUARDRAIL` | `PASS` | Zurich location resolution succeeded; FEMA capability description rejected the request as outside declared geographic coverage. The trace contains no provider retrieval or map render call. The attempted map request correctly ended blocked. |
| `T0-04` | `PARTIAL` | The inherited non-empty `AEGIS_DATA_DIR` override passed fresh and warm official-launcher checks with an isolated healthy database. See [environment precedence](launcher-env-precedence.log), [fresh launch](launcher-process-override.log), [warm launch](launcher-warm-start.log), and [isolated database check](isolated-db-readonly-check.txt). Paired optimization timing, provider outage, changed-owner races, and injected service-failure cleanup remain unverified. |
| `PROCESS-CLEANUP` | `PASS` | Task-owned services were stopped and ports 4512, 7059, and 9876 were confirmed free. The user-owned Chrome tab was left open. Isolated runtime data was retained because it contains the provider configuration the user just saved. |

The campaign roll-up is 19 `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 47 `UNRUN` of 68 slices. The two partial campaign slices are `T0-04` and `T2-04`. `T2-01` and `T2-02` now pass; `T2-03` remains passed. `T2-05` through `T2-07` remain `UNRUN`.

Other open boundaries remain distinct: the full route and browser matrix is `PARTIAL`; the broad browser diary is `PARTIAL`; live FEMA/ESA raster loading and dependent composition remain limited, with `GEO-HYD-05` and `GEO-HYD-06` still `BLOCKED`; provider parity remains `BLOCKED`; and dataset ingestion remains unvalidated. See the canonical ledgers for the complete gate inventory.

## Focused backend validation

Using `app/server/.venv`, this command passed:

```text
python -m pytest -c app/server/pyproject.toml -p no:cacheprovider --basetemp=runtimes/cache/pytest-tmp/t2-final-validation-ledger-v2 \
  app/tests/unit/services/agent/test_agent_loop_v2.py \
  app/tests/unit/services/agent/test_capability_router.py \
  app/tests/unit/services/agent/test_catalog_tool_handler.py \
  app/tests/unit/services/agent/test_location_resolver.py \
  app/tests/unit/services/agent/test_location_resolver_country_contract.py \
  app/tests/unit/services/agent/test_location_tool_handler.py \
  app/tests/unit/services/agent/test_tools.py \
  app/tests/unit/test_nominatim_service.py
```

Result: **155 passed**, 1 warning, in 1.00 second. The warning is the existing `PytestConfigWarning: Unknown config option: cache_dir`.

Ruff passed on all modified Python implementation and focused-test files. `git diff --check` passed after ledger reconciliation.

## Remaining T2-04 work

The live run is `run_e736054311d241b8b53b1b73205e2de1`. The model-call guard stopped continuation after three successful pages and four model calls total. The code path that silently advances inventory beyond the configured model-call guard was not used. Full inventory validation still needs an explicitly approved runtime budget adjustment or a bounded continuation policy that respects that guard. Once authorized, continue from the remaining catalog cursor and verify the UI completion state without requesting a map.

## Hosted CI follow-up

The first pushed implementation commit, `29115ee0c62af70a7e3e40c9bdbaaacc11f8ccaa`, triggered [GitHub Actions run 36050255036](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36050255036). The backend job stopped at strict Pyright because the route normalizer inferred a partially unknown type for an empty/update dictionary. The route update now uses explicit branches. After the repair, repository Pyright reports 0 errors, 0 warnings, and 0 informations; the focused capability-router suite passes 23 tests, and Ruff passes. See the `hosted-static-fix-pyright.log`, `hosted-static-fix-pytest.log`, and `hosted-static-fix-ruff.log` artifacts. A follow-up push will provide the final hosted result.

## Evidence and cleanup

Rendered browser observations and run IDs are in [`browser-evidence.md`](browser-evidence.md). The in-app Browser did not export a local screenshot, so no screenshot artifact is claimed. The Settings key value, raw provider payloads, and secrets are absent from committed files. The configured isolated runtime database was retained; only task-owned service processes were stopped. The shared runtime database was opened read-only for an integrity check, and its pre/post file metadata snapshots match ([before](canonical-db-metadata-before.txt), [after](canonical-db-metadata-after.txt), [read-only integrity check](shared-runtime-readonly-check.txt)).
