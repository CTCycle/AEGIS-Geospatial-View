# Agent-loop reliability — BASELINE (before audit changes)

- Date: 2026-11-05. Code: `develop` @ `b49c699b` (clean tree at start; other sessions edit concurrently, backend ran **without** `--reload`, so it served the code loaded at its start, ~23:12 local; later develop commits `25f7374a` (23:14) and `cc66a4dd` (23:23) are not in the measured code unless a module was imported lazily after those edits landed).
- Lane: OpenCode Go / DeepSeek v4.1 Flash only (verified in run events `provider=opencode-go model=deepseek-v4.1-flash`). No fallback model. UI driven in the built-in browser, fresh conversation per scenario.
- Suite: [scenarios.md](scenarios.md) (16 scenarios, 67 obligations). Per-run raw numbers: [run-metrics.txt](run-metrics.txt). Screenshots: `S01.jpg`–`S16.jpg` (final UI state of each scenario).
- Harness notes: backend started with `FASTAPI_PORT=5002 UI_PORT=5000` process overrides because the local `settings/.env` uses other ports and the WebSocket origin check (403) otherwise blocks the UI. Viewport emulated at 1440x900 (UI refuses < 1024px). Verdicts judge answer text + persisted run events/evidence + the visible map together; backend `goal_satisfied` was never used alone.
- Scenario text clarified once during the run: S02-O4 now says two unlabelled markers do not count as showing the temperatures/difference (clarified after S02, before any later scenario).

## Aggregate

| Metric | Baseline |
| --- | --- |
| Scenarios PASS / FAIL | **7 / 9** (S01 S04 S05 S09 S10 S12 S14 pass) |
| Obligations met / total | **51 / 67 (76%)** |
| False successes (claimed done, wrong/incomplete) | **3 firm** (S02, S13, S15) + 1 partial (S08-T1) |
| Invalid tool calls (semantic validation / not exposed / policy rejection; clarification requests excluded) | **6** (S07: 3, S13: 2, S16-T1: 1) |
| Redundant provider calls | **1** (S13 unrelated IMERG precipitation fetch) + 2 needless `inspect_evidence` (S02) |
| Redundant model iterations | S01 4 of 8 calls were `no_progress` loops; S07 ran 10 calls / 546 s before manual cancel |
| Unnecessary render attempts | **5** (S07 ×2 on empty data, S08 ×1 retry after timeout, S09-T1 unrequested map, S11-T2 identical map) |
| Cross-turn evidence reuse | 6 of 6 reuse opportunities used it (S08-T2, S09-T2 places, S11-T2 place, S12-T3/T4/T5) — reuse works; failures are elsewhere |
| Runs total / provider_rate_limited (HTTP 429, zero tokens) | 36 / **9** (25%); each retried in a fresh conversation, only the retried run is judged |
| Run wall time (started→completed, excl. render-ack wait) | typical 2–23 s; slow tail: S13 52 s, S07 stalled 546 s (cancelled) |
| Tokens (reported, all 36 runs) | 976k input / 22.8k output; worst turn S13 120k in; S12-T4 (a pure comparison) 69k in; S09-T2 101k in |

## Per-scenario results

Obl = obligations met/total. Model calls and tokens are summed over the scenario's judged runs (from `agent_run_events`).

| id | Verdict | Obl | Model calls / tokens in·out | Notes (what was observed) |
| --- | --- | --- | --- | --- |
| S01 info question, no map | **PASS** | 4/4 | 8 / 40.2k·1.4k, 17 s | Zurich resolved, one Open-Meteo call, temperature correct, no map. Waste: 4 `no_progress` iterations on pending `temporal_scope_applied`, run decision `fail: insufficient_evidence` (state still `completed`), and the answer appends a spurious "Not completed: time window not verified". |
| S02 Lugano vs Milan compound | **FAIL** | 4/5 | 7 / 65.8k·1.5k | Both cities, both temps, difference 1.1 °C correct. **Map shows two markers with names only — no temperatures, no difference** (O4). Answer claims values are "shown… graduated by °C" → false success. 2 needless `inspect_evidence`. |
| S03 Brandenburg Gate | **FAIL** | 1/3 | 1 / 2.9k·0.1k | Resolver typed `landmark` but returned a clarification (Berlin gate vs. a Kaliningrad street) for a world-famous landmark. No map. Honest but unhelpful. |
| S04 Rome | **PASS** | 3/3 | 2 / 6.0k·0.2k | 1 resolve + 1 map plan, centred on Rome. |
| S05 Springfield → Massachusetts | **PASS** | 4/4 | 4 / 13.6k·0.5k | T1 clarified (IL/MA), T2 resolved MA and mapped it. |
| S06 ambiguous tool (Wellington wind + weather) | **FAIL** | 1/4 | 4 / 6.3k·0.3k | Attempt 1: 429. Attempt 2: clarification Wellington NZ vs Texas, so the tool-choice behaviour was never exercised (scenario-design weakness: place ambiguity masks it). No data returned. |
| S07 impossible magnitude (M15, Japan) | **FAIL** | 1/4 | 10 / 51.8k·1.2k, **546 s** | USGS correctly `valid_empty`, but the loop kept going: `tool_not_exposed`, 2× `semantic_validation_failed` on `apply_map_plan` (map of an empty result), model-call stalls. Never answered; cancelled by hand. No fabricated events. |
| S08 earthquakes → strongest | **FAIL** | 3/4 | T1 10 / 102.8k·2.8k; T2 3 / 18.8k·0.5k | T1: USGS fetched (90 events → filtered/limited to **25** for the layer), but **render ack timed out twice, map blank**; answer says "I've prepared the map" and only later admits it was unconfirmed (partial false success). T2: answered from stored evidence via `inspect_evidence`, **no new USGS call** (M6.1 Fiji region, top of the descending-sorted evidence). Re-run for a clean T1 was blocked by two more 429s. |
| S09 temperatures → precipitation | **PASS** | 5/5 | T1 6 / 42.9k·1.5k; T2 5 / 100.8k·1.8k | Three places resolved once and reused in T2; precipitation fetched fresh (3 calls), no temperature refetch. Defects: T1 (information question) drew a map anyway; map labels show names only. |
| S10 30 days → 24 h | **PASS** | 5/5 | T1 6 / 43.4k·1.3k; T2 6 / 67.8k·1.2k | T2 issued a new 24 h USGS query, M5 carried over, 3 events, honest. Defects: the 205-event result is cut to **25 by `transform_evidence limit`** for the map; T2 leaves the old 30-day layer on the map (disclosed in the answer). |
| S11 unchanged map re-request | **FAIL** | 3/4 | T1 2 / 6.0k; T2 2 / 12.5k | Attempt 1: 429. T2 did not recognise the map already shows Lisbon: a second identical `apply_map_plan` (unnecessary render). No provider call, truthful answer, map unchanged. |
| S12 long conversation (5 tasks) | **PASS** | 6/6 | 18 / 178k·2.9k | Vienna map → Vienna temp → Prague temp (no Vienna refetch) → "Vienna warmer by 1.1 °C" from evidence only (no provider call) → Prague map. Defects: T4 cost 69k input tokens, T5 37.9k for a map move, T5 text ("Map state update verified… overlays: none") never names Prague. First attempts: 3× 429 + 1 render timeout before a clean run. |
| S13 wildfire hotspots Portugal | **FAIL** | 3/5 | 14 / 120.5k·2.9k, 52 s | MODIS fire layer is a **raster** (no records); loop tried `grid_aggregate` (unsupported), fetched an **unrelated IMERG precipitation** layer, retried overlay (semantic validation). Render failed, **map blank**, yet the answer says "What's on the map: NASA GIBS thermal-anomaly overlay" and, a paragraph later, "no map was prepared" → false success / contradictory. |
| S14 haiku | **PASS** | 3/3 | 2 / 5.1k·0.1k | Direct text, no tools, no map. |
| S15 numeric coordinates | **FAIL** | 3/4 | 3 / 9.3k·0.3k | Coordinates parsed, map centred on Lugano. **The "tell me what place that is" half was ignored** (answer: "The map now shows 46.0037, 8.9511…") and presented as complete → false success. |
| S16 radar then clear | **FAIL** | 2/4 | T1 3 / 12.6k·0.4k; T2 7 / 30.3k·0.8k | T1: radar capability rejected (`outside declared coverage`) and the raw policy string was returned as the whole answer, no alternative layer. T2 ("just show Tokyo"): resolved Tokyo twice, then said **no map-preparation tool was available this turn**, no map shown (route carried over from T1's text-only state). |

## Failure themes (for the audit areas)

1. **Presentation without semantics** (S02, S09, S10, S13): maps get layers whose values/legend are not visible, and answer text claims what is on the map without checking it. No closed loop between the stated presentation and what rendered.
2. **Obligation loss across compound requests** (S15 dropped the place-name question; S02 "show the difference" reduced to two markers).
3. **Intent class carried over wrongly** (S16-T2: stale text-only route blocks a simple map request; S09-T1: info question drew a map).
4. **Unbounded/low-value iteration** (S01 four no-progress loops; S07 and S13 spend 10–14 model calls on dead ends, including an unrelated provider call and map plans on empty data).
5. **Tool-contract friction** (6 invalid calls: not-exposed tool, semantic validation on `apply_map_plan`/`execute_geospatial_capability`, grid aggregate on raster, policy rejection surfaced raw).
6. **Disambiguation too eager** for famous landmarks (S03) and generic ambiguity masking (S06).
7. **No "already shown" short-circuit** (S11).
8. **Silent truncation**: 90/205 events reduced to 25 for the map via `transform_evidence limit` (S08, S10) — verify the answer discloses it.
9. **Environment**: 25% of runs hit provider 429 (`provider_rate_limited`) and a wall-clock stall appeared (S07); not agent-loop logic, but they dominate wall time and mask results. Possibly caused by other sessions sharing the same OpenCode Go key; treat re-run variance accordingly.

## Re-run protocol

Same backend flags (no `--reload`, `FASTAPI_PORT=5002 UI_PORT=5000`), same model, prompts verbatim from `scenarios.md`, fresh conversation each, reload the page before starting a scenario if a map render ever times out. Rerun any run that fails with `provider_rate_limited` (record it) and judge the retried run. `run-metrics.txt` columns: conversation, run, state, presentation status, duration, model calls, tokens in/out, tool count, `apply_map_plan` count, failed tool codes, request.
