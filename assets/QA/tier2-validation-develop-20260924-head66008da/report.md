# Tier 2 validation recheck on `develop`

Date: 2026-09-24
Branch: `develop`
Tested source: `66008da15ea4ea23a5b1e99090441438bb163fba`
Working tree before validation: clean and matched `origin/develop`.

## Scope and result

| Gate or slice | Result | Evidence and boundary |
| --- | --- | --- |
| `ROUTE-UNIT` | `PASS` | Five focused native test modules: 103 passed on the tested source. This is local contract/regression evidence, not exact-provider proof. |
| `CONTROLLED-HAPPY` | `PASS` | Visible MapLibre completion reached `ready`; the browser emitted a matching `map.render_ack` for run, session, and collection revision. |
| `CONTROLLED-FAULT` | `PASS` | Complete `app/tests/e2e/test_agentic_map_completion.py` module: 10 passed. The WebSocket fixture injects controlled faults; the browser performs the MapLibre acknowledgement checks. |
| `T2-01` | `PARTIAL` | Focused routing/location regressions pass, but the exact-lane browser scenarios were not started. Prior Milan candidate quality and the `Rodano` label remain unresolved. |
| `T2-02` | `PARTIAL` | Focused routing/location regressions pass, but the exact-lane Florence transition was not started. Prior ambiguous Florence behavior replaced Rome without clarification and remains unresolved. |
| `ROUTE-LIVE` / live diary | `PARTIAL` | Exact `opencode-go / deepseek-v4.1-flash` was unavailable in this isolated app configuration; no provider request or fallback was used. |
| Windows launcher smoke | `PASS` for the smoke check | The official launcher reached backend and frontend health in the isolated runtime. This does not close the broader startup component's paired-timing, provider-outage, ownership-race, or injected-failure-cleanup gaps. |
| Task process cleanup | `PASS` | Task-owned backend/frontend processes stopped; ports 4512, 7059, and 9876 were free; repository `settings/.env` was restored byte-for-byte. |

## Evidence

### Focused backend routing tests

Command, run with `app/server/.venv`:

```text
python -m pytest -c app/server/pyproject.toml -p no:cacheprovider --basetemp=runtimes/cache/pytest-tmp/t2-20260924-head66008da \
  app/tests/unit/services/agent/test_agent_loop_v2.py \
  app/tests/unit/services/agent/test_capability_router.py \
  app/tests/unit/services/agent/test_location_resolver.py \
  app/tests/unit/services/agent/test_location_resolver_country_contract.py \
  app/tests/unit/services/agent/test_location_tool_handler.py
```

Result: **103 passed**, 1 pytest configuration warning, in 0.64 seconds. The
warning is `PytestConfigWarning: Unknown config option: cache_dir`; the cache
plugin was disabled intentionally for the isolated run.

Full output: [focused-backend.log](focused-backend.log).

### Controlled browser module

Command:

```text
python -m pytest -c app/server/pyproject.toml -p no:cacheprovider --basetemp=runtimes/cache/pytest-tmp/t2-map-fault-20260924-head66008da app/tests/e2e/test_agentic_map_completion.py
```

Result: **10 passed**, 1 same pytest configuration warning, in 28.86 seconds.
Nine scenario JSON reports and nine browser screenshots were retained. The
happy path records a `ready` presentation, loaded source/layer, visible feature,
and accepted acknowledgement for `controlled-map-run-1` /
`rome-earthquake-session` / collection revision 7. The other reports exercise
cancelled, duplicate acknowledgement, failed layer, mismatched acknowledgement,
retry exhaustion, stale acknowledgement, supersession, and viewport mismatch.

- [Full module output](controlled-fault/full-module.log)
- [Happy-path scenario report](controlled-fault/reports/controlled-map-completion.json)
- [Happy-path screenshot](controlled-fault/screenshots/__test_controlled_map_completion_requires_and_records_visible_rendering%5Bchromium%5D/controlled-map-completed.png)
- [All scenario reports](controlled-fault/reports/)
- [All scenario screenshots](controlled-fault/screenshots/)

The browser module is a controlled local fixture. It does not establish public
FEMA/ESA raster loading, provider availability, or live end-to-end location
routing.

### Exact-lane readiness and launcher

The official Windows launcher started the isolated app on ports 7059 and 4512.
In the rendered Settings screen, no agent model was selected and the OpenCode
Go API key was not configured. Therefore, the exact
`opencode-go / deepseek-v4.1-flash` location flows and Zurich coverage guardrail
were blocked before request execution. No live provider call was made and no
other model/provider was substituted.

The original `settings/.env` SHA256 was
`95D56835BADD0DD60AEDA6662D382BAFB0F76D3A75DA4D09B95F0165D98606FC` before
and after the isolated run. Task-created runtime and pytest scratch paths were
removed after validation. The task-created browser tab was closed and the
three task-owned ports were confirmed free. Existing protected QA cache paths
were not touched.

### Hosted CI for the validation commit

After the evidence and ledger update was committed and pushed as
`0113812c7e4e1945c9a2846bec1942c6889a7264`, GitHub Actions run
[36003422893](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36003422893)
completed successfully. All four jobs passed: `backend-unit-tests`,
`persistence-conformance`, `capability-contract-validation`, and
`frontend-build-and-tests` (including frontend build, unit tests, and
geospatial browser smoke). GitHub emitted Node.js 20 deprecation and upcoming
`ubuntu-latest` image migration notices; these were warnings and did not fail
the run.

## Final status and remaining work

No product source or test code changed. `ROUTE-UNIT`, `CONTROLLED-HAPPY`, and
`CONTROLLED-FAULT` pass at the tested source boundary. Keep `T2-01`, `T2-02`,
`ROUTE-LIVE`, the live diary, and the complete matrix `PARTIAL` until the exact
provider/model can be selected and configured and the browser scenarios are
rerun. In particular, retain the Milan candidate/`Rodano` quality issue and
require clarification before an ambiguous Florence request replaces Rome.

The Zurich FEMA guardrail was not executed. Public FEMA/ESA renderer loading,
`GEO-HYD-05/06`, capability discovery, direct tools, history, evidence
inspection, and broader Tier 3–5 campaign gates remain `PARTIAL`, `BLOCKED`, or
`UNRUN` as recorded in the ledgers. The local controlled run does not change
those outcomes.
