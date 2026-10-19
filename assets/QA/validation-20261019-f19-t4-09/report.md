# 2026-10-19 F-19 USGS dated ranges, T4-09 lane parity, harness repairs

Starting SHA `develop@7343ba62` plus the working-tree fixes listed in [slice.json](slice.json). Lane: exact `opencode-go / deepseek-v4.1-flash` on an isolated disposable runtime (backend 5079, Angular 5080, database copied into `runtimes/cache`, removed afterwards; the user's own 4512/7059 app was left untouched). The credential was never written to these artifacts.

## Scope selected
Ledger review left two actionable items that need no new credentials or hardware: F-19 (explicit USGS time ranges, open since 2026-10-18) and T4-09 (Tier 4B, the only live lane). Everything else open was re-checked and left unchanged for the reasons in "Not covered".

## Results

| Item | Result | Evidence |
| --- | --- | --- |
| F-19 explicit USGS ranges | CLOSED, with an upstream-latency limitation | Live: "Japan, 1-7 March 2024" completed, `presentation=ready`, 20 events, clustered points, USGS attribution, scope stated in the answer ([screenshot](screenshots/f19-japan-march-2024-week-render.png)). "Perth, 2024-03-01 to 2024-03-07" returned an honest `valid_empty`, map preserved on Perth ([screenshot](screenshots/f19-perth-valid-empty-map-preserved.png)). |
| T4-09 OpenCode Go lane parity | PASS (reconstructed acceptance, LOW confidence) | [run-summary.json](run-summary.json): the Japan run used 5 model calls and `describe` -> `execute` -> `apply_map_plan`; the Perth run 6 calls across location, describe, execute, map plan. A transient `provider_api` model failure (1 run, zero tool calls) ended as a clean failed run with a plain message; the next run succeeded. Rejected thinking/temperature learning is covered by the commit `5842ffc9` unit tests and vision capture by the existing VISION-INSPECT PASS; neither was re-run live here. |
| Regression smoke: F-13 radar, Naples | Not re-promoted | Tiles proxied and loaded but 0 non-transparent pixels (no precipitation over the viewport at test time); backend rejected the render honestly. Weather-dependent, so neither a pass nor a regression. F-13's earlier live PASS stands. |

## Defects found and fixed
1. **USGS adapter was current-only.** `_earthquakes` only read rolling summary feeds. It now queries the FDSN catalog when a start time is present (`startTime`/`end_time_iso`, bbox pushed upstream when not antimeridian-crossing, 2,000-event cap with a warning, 366-day limit, inverted/over-long ranges rejected). The manifest now declares `historical` / `dated_range`.
2. **Per-provider timeouts were ignored inside agent runs.** `turn_runner` scopes a generic run policy that replaces the configured one, so `provider_timeout_seconds` never applied to agent runs. `ProviderRegistry._timeout_seconds` now keeps the configured per-provider floor; USGS gets a 40 s deadline (tool deadline is 45 s). FDSN measured 9-38 s live.
3. **Date-only temporal scopes always failed the completion check.** `CompletionEvaluator.assess_evidence` compared a naive date with an aware observation time (`TypeError`, swallowed as "unknown"), so the backend rejected every dated-range map with `temporal_scope_applied`. Dates are now parsed as UTC and a date-only end bound covers its whole day. This affected any historical range request, not only USGS.
4. **Harness:** three live e2e modules imported `_provider_probe`, removed by `b9e3874f`, so unit collection failed. They now use a shared `exact_lane_tool_support_metadata` helper. `test_canonical_schema...` and `persistence.md` still said 18 tables after `model_probe_results` was dropped; both now say 17.

## Open finding (not fixed)
**F-26:** for an unresolvable place name, date text such as "March 7, 2024" was parsed as a coordinate pair ("7, 2024 is outside coordinate bounds"). Observed with "Point Nemo ... from March 1 to March 7, 2024".

## Limitations
- A full-month Japan query timed out at the 40 s deadline in one live run (two earlier runs of the same query completed upstream in 9-15 s). USGS catalog latency is external; the failure was reported honestly with no empty layer drawn. The one-week window is the render proof.
- Only one successful live range-render run per case; no load or repetition claim.

## Quality gates (final working tree)
1,140 backend unit tests pass ([log](logs/full-unit.log)); Ruff clean ([log](logs/ruff.log)); strict Pyright 0/0/0 ([log](logs/pyright.log)); strict production manifest audit 0 errors, 0 warnings ([log](logs/manifest-audit.log)). Frontend sources unchanged, so Angular build/Karma were not rerun.

## Not covered, and why
T4-10 to T4-13 and T5-11 (no OpenAI/Google/Zen credentials or Ollama; never substituted), T5-13 (theme unresolved), T4-06 (no camera source), T4-05 (no configured external source), T4-07 (OpenTripMap key absent), T4-03 (no heavy-format normalizers; a feature, not validation), Overpass reliability (external), numeric elevation (licence opt-in).

## Cleanup
Backend and frontend stopped; ports 5079/5080 verified free; disposable runtime and temp pytest directories removed; stray `.ruff_cache` removed. `.playwright-mcp` is gitignored.
