# Tier 2 location validation report

Validation date: 2026-09-23

## Result

`T2-01` and `T2-02` are `BLOCKED` for current-head live validation. The
required official launcher built the frontend but did not make the backend
healthy within its 60-second readiness window. The in-app browser then showed
`ERR_CONNECTION_REFUSED` for `http://127.0.0.1:4512/`. No user workflow, map,
attribution, or `map.render_ack` was produced. The blocked attempt is not a
slice pass, even though focused backend tests passed.

The live active-run `409` recheck for `LIVE-API` is also `BLOCKED` on this
attempt. Its previous exact-lane live pass is historical evidence at the T1-06
boundary, not a recheck on this source head.

## Source and environment boundary

- Branch and application source SHA: `develop@155e1e22ce34a4b2698f474afa60b57f61b56916`.
- No application source changes were made.
- The runtime data path was isolated at
  `runtimes/cache/test-runtime/tier2-20260923`.
- A diagnostic settings read confirmed the selected lane was `opencode-go /
  deepseek-v4.1-flash` and reported a configured credential. No credential
  value was read into this report. This confirms configuration only, not a
  successful provider run.
- `start_on_windows.ps1 -Action Launch` used the official launcher. The
  production frontend build succeeded; the launcher then timed out waiting
  for backend health at `127.0.0.1:7059/api/health` and cleaned up its child
  processes. The captured [launcher output](official-launcher-pwsh-stdout.log)
  records the build and readiness timeout; the underlying startup cause was
  not established.
- The temporary `settings/.env` edit was restored byte-for-byte. Ports 4512,
  7059, and 9876 were verified free after cleanup.

## Slice outcomes

| Slice | Status | Current-head result | Remaining proof |
| --- | --- | --- | --- |
| `T2-01` | `BLOCKED` | Direct place navigation, Springfield clarification/resolution, invalid-coordinate prior-map retention, and `Mostrami Milano` were not exercised because the app was unreachable. | In-app map must show the resolved geography or safe clarification, expected viewport, visible basemap attribution, and matching run/session/revision acknowledgement. Recheck Italian context; the earlier `Mostrami Milano` result remains an attention item because it did not prefer Milan, Italy. |
| `T2-02` | `BLOCKED` | Hydration, Rome → ambiguous Florence, and explicit Florence, Tuscany, Italy replacement were not exercised on this head. | Show Rome remaining while Florence is ambiguous, then the Florence, Tuscany, Italy viewport, visible attribution, and matching run/session/revision acknowledgement. |

Historical context: the [2026-09-19 core browser report](../core-behavior-e2e-20260919/final-report.md)
covered Springfield and invalid-coordinate behavior, and the [2026-09-19
geospatial diary](../aegis-geospatial-e2e-validation-20260919/report.md)
rendered Florence after clarification. Those results were on different source
boundaries and do not replace this blocked current-head attempt.

## Related live API gate

The focused API contract test
`test_chat_turn_returns_409_only_for_real_run_conflict` passed as part of the
current-head suite, but its test stub does not prove a timed live active-run
conflict. T1-06 recorded a genuine live `409` on its earlier exact-lane
boundary; the current official launcher never exposed a healthy API, so
`LIVE-API` remains `PARTIAL` and its requested live recheck is `BLOCKED`.
The separate Ollama-unavailable `502` boundary remains unchanged.

## Checks

The focused current-head command covered location resolver, native agent loop
v2, and chat contract tests:

```powershell
$env:PYTHONPATH = "app"
.\app\server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=.\runtimes\cache\pytest-tmp\tier2-20260923-elevated -q .\app\tests\unit\services\agent\test_location_resolver.py .\app\tests\unit\services\agent\test_agent_loop_v2.py .\app\tests\unit\api\test_chat_contracts.py
```

Result: `74 passed`, with two upstream deprecation warnings. The first,
un-elevated attempt failed before tests ran because sandbox setup of the
required isolated pytest temporary root was denied with `WinError 5`; the
elevated rerun passed. Its temporary data was removed afterward.

No backend or frontend code changed, so Ruff and Angular regressions were not
rerun. No regression test was added because no in-scope implementation defect
was observed; live behavior remained unobservable.

## Remaining scope

The campaign remains `PARTIAL`: `17 PASS`, `0 PARTIAL`, `2 BLOCKED`, and `49
UNRUN` of 68 slices. Retry `T2-01` and `T2-02` when the official launcher can
reach backend health, then continue with the separate `T2-03` landmark/POI
routing work tracked by `ISSUE-001`.

Other recorded limitations remain open: route-matrix gaps; coordinate reverse
geocoding and provider availability; RainViewer, EEA, PVGIS, and Census routing;
FEMA/WorldCover raster loading and dependent composition; acknowledgement
supersession ordering; startup timing/cleanup; ingestion coverage; and blocked
provider/credential parity. No broader gate is promoted by these focused
tests.
