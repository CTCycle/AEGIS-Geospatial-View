# 2026-10-19 Tier 5 recovery slice (T5-04, T5-05, T5-06) and leftovers

Branch: `develop`. Starting SHA: `817f3242` (clean). Tested source: that SHA plus the working-tree change listed in [slice.json](slice.json) (committed afterwards; the commit SHA is recorded in the ledger).
Lane: exact `opencode-go / deepseek-v4.1-flash` on an isolated disposable runtime (backend 127.0.0.1:5079, Angular dev server 5080, data root copied from the configured database into `runtimes/cache`, removed afterwards). The credential was never written to these artifacts. Tier 5 IDs keep the LOW-confidence reconstructed mapping.

## Result summary

| Item | Result | Evidence |
| --- | --- | --- |
| `T5-05` restart recovery | `PASS`, no product defect | Hypothesis disproved: the planning assumption that orphaned runs are never reconciled was wrong. `RunLifecycleService.resume_active_runs` requeues non-terminal runs at startup. See below. |
| `T5-07` stream/job entry points | extended, defect fixed | `/api/chat/stream` returned HTTP 200 with a raw pydantic message in an `error` event (`1 validation error for AgentRunCreateRequest ...`); `/api/chat/jobs` accepted the request (202) and failed later. Both now return 422 with the sanitized `message is too long` / `message must not be empty` detail and echo no input ([before](http/stream-job-oversize-before-fix.json), [after](http/stream-job-oversize-after-fix.json)). Regression test parametrized over turn/stream/jobs. |
| `T5-04` outages | `PASS` (two fixtures, see limits) | Browser evidence below. |
| `T5-06` repetition | `PASS` for the location-only boundary | [11 runs](http/t5-06-repetition.json): 8 fresh conversations and 3 repeats in one conversation, identical prompt, all HTTP 200 `prepared`, 4.0-5.8 s each, backend RSS 223.8 MB to 226.1 MB (+2.3 MB). After the run: SQLite `integrity_check` ok, 0 rows with `active_slot=1`, no conversation with more than one `awaiting_render` run. |
| F-13 radar leftover | `PASS` | Browser run "Show the current precipitation radar at Naples, Italy." rendered RainViewer, run `completed`, presentation `ready`; narration named the correct layer, attribution, observation time and the zoom-6/7 limits ([screenshot](screenshots/f13-radar-naples-rendered.jpg)). |
| Census cartographic-boundaries descriptor | documented, not changed | `census_cartographic_boundaries`, `eurostat_nuts_regions` and `natural_earth_admin_boundaries` are shapefile *downloads* declared `renderingMode: vector-tile` with no tile URL. `render_descriptors.py` already degrades them to metadata-only with a warning and the agent falls back to the TIGERweb overlay. Making them renderable needs the shapefile normalizers that `T4-03` lacks; relabelling three manifests would only hide that gap. |

## T5-05 restart recovery

Method: start a turn, confirm `active_slot=1` / `running` in SQLite, `taskkill /F /T` the backend, restart on the same data root.

- API run 1 (parks prompt, killed at iteration 4): after restart the run was resumed from the start (`run_started` appears twice in the [trace summary](http/t5-05-resumed-run-trace-summary.json)), kept the slot, and a follow-up received **409 while it executed**, which is correct. It ended `failed: The agent stopped after repeated invalid tool calls` after two `policy_rejection` tool calls. An uninterrupted control run of the same prompt succeeded in 35 s, so this is model variance on a hard prompt, not a restart fault, but it is recorded rather than hidden. ([before-fix probe](http/t5-05-before-fix.json), [state](http/kill_state.json))
- API run 2 (weather prompt, killed `running`): early follow-up 409, resumed run `completed`, later follow-up 200, no stuck slot ([cycles](http/t5-05-cycles-12.json)). Cycles 1 and 3 finished before the kill (`pre_kill_state` null; `awaiting_render` at kill, follow-up supersedes it cleanly) and are not counted as in-flight evidence ([cycle 3](http/t5-05-cycles-3.json)).
- Browser run (weather in Madrid): backend killed mid-run, down about 26 s. The client's backoff reconnect succeeded after restart, the resumed run completed with presentation `ready`, and the Madrid map rendered with two Open-Meteo layers ([during outage](screenshots/t5-05-browser-during-outage-pre-reconnect.jpg), [after](screenshots/t5-05-browser-after-restart-resumed-run.jpg)).
- Not tested: kill during a render acknowledgement exchange, and kill mid-persistence. A resumed run re-executes from the beginning rather than from a checkpoint.
- Harness note: the dev server needs the backend started with `UI_PORT=5080`, otherwise the realtime origin check returns 403 (visible in the first browser attempt's logs).

## T5-04 outages (browser, same conversation)

1. Model outage: Rome then Naples rendered; the isolated runtime's OpenCode Go credential was replaced with an invalid test value. "Show me a map of Milan, Italy." ended `failed` with `The selected model could not complete this request.`, no spinner, the Naples map preserved, status bar "Agent model: Needs attention" ([screenshot](screenshots/t5-04-model-outage-naples-preserved.jpg), [run rows](http/t5-04-model-outage-runs.json)). After restoring the healthy credential from a pre-fault snapshot, Milan rendered and the indicator returned to "Verified" ([screenshot](screenshots/t5-04-model-recovered-milan.jpg)).
2. Geospatial provider outage: the Open-Meteo weather base URL was set to an unreachable address through the runtime settings API. The weather request ended after 74 s with an honest message ("Both available weather sources failed ... I did not add a weather layer ... The Milan map itself is still available"), the Milan map preserved and no partial layer ([screenshot](screenshots/t5-04-geo-outage-honest-failure-map-kept.jpg)). After restoring the setting the same request rendered the forecast layers ([screenshot](screenshots/t5-04-geo-recovered-weather-milan.jpg)).
- Limits: the "model outage" is a rejected credential, not a network partition (an outbound dead proxy had no effect on the LLM client, so it was abandoned); selecting a nonexistent Ollama model is refused at Settings (400), which is a separate valid guard. The 74 s failure is inside the run deadline but slow for the user.

## Quality gates

- Full backend unit suite: **1,130 passed** ([log](logs/full-unit.log); the two extra tests are the new stream/job cases). Ruff: all checks passed ([log](logs/ruff.log)). Strict Pyright: 0 errors, 0 warnings, 0 informations ([log](logs/pyright.log)).
- Frontend sources were not changed; Angular build and Karma were not rerun.
- No manifest changed; the manifest audit was not rerun.

## Not covered, and why

- `T5-09` performance and `T5-10` accessibility: no authored contract; passing them would require inventing thresholds. The T5-06 latencies are input for a future contract only.
- `T5-11` and `T4-09`-`T4-13`: no approved credentials or local server for OpenAI, Google, DeepSeek/OpenCode Zen or Ollama. `T5-13`: theme unresolved.
- F-19 (USGS explicit time ranges), Overpass reliability, `T4-03` normalizers, `T4-05`/`T4-06`/`T4-07`, numeric elevation (licence opt-in) and FEMA scale-dependent composition are unchanged.
- T5-06 covers one prompt class (location-only map) on the exact lane; weather/raster repetition and long-session growth are not claimed.

## Cleanup

Task-owned backend and frontend processes stopped; ports 5079, 5080, 4512, 7059, 9876, 8000 and 8001 verified free; the disposable runtime (including its database copy and snapshot) and temp pytest directories removed. Probe scripts lived in the session scratchpad.
