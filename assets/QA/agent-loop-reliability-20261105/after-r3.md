# Agent-loop reliability — AFTER R4–R6 remediation (`develop@080cc59a`)

- Date: 2026-11-06. Fourth live measurement of the frozen suite. Columns: **baseline** (`b49c699b`, [baseline.md](baseline.md)), **after** (`6c954aea`, [after.md](after.md)), **after-r2** (`6e3404c8`, [after-r2.md](after-r2.md)) and **after-r3** (`080cc59a`, this run; R4 `1575a3ef`, R5 `4feb14ae`, R6 `080cc59a`).
- Setup identical to the earlier runs: backend from `app/` (`server.app:app`) on 5002, **no `--reload`**, `FASTAPI_PORT=5002 UI_PORT=5000`, UI by `ng serve --port 5000`, built-in browser at 1440x900, fresh conversation per scenario, prompts verbatim from [scenarios.md](scenarios.md). Lane: OpenCode Go / DeepSeek v4.1 Flash only, verified in the `context_usage` events of every run. HEAD clean apart from the untracked `app/app/`.
- **No model-provider 429 and no data-provider rate limit** this round: 26 judged runs, nothing retried. Consequence: R6's rate-limit recovery path (one retry, then honest per-target failure) was **not exercised live**.
- Raw numbers: [run-metrics-after-r3.txt](run-metrics-after-r3.txt) (26 judged runs + 4 unjudged probe runs, marked). Screenshots: `after-r3-S01.jpg` … `after-r3-S16.jpg` (final UI state; S10, S12, S16 show the last turn). **There is no S06 screenshot** (text-only scenario; I did not capture the final state before starting the next chat).
- Verdicts judge answer text + persisted run events + the visible map together, same obligations as the baseline. Each scenario was run once; completed scenarios were not re-run (protocol), so every row is a single sample. After the suite I took **two unjudged probe repeats** (S16 and S08, one fresh conversation each) because those were the two worst new failures; they are reported separately and change no verdict.

## Headline

R4–R6 fixed most of what they targeted: **S02, S06, S08-T1, S10-T2 are fixed**, invalid tool calls fell **10 → 4**, S02 dropped from 195k to 52k tokens, S10-T2 from 94k to 33k. But the run found **three new degradations** and **two targets not fixed**:

1. **S08-T2 returns no answer** ("The requested work finished, but the model returned no answer text."), run state `completed`. Reproduced in the probe (2 of 2 samples), so it is not a one-off. After-r2 answered this correctly.
2. **S12-T4 is still expensive (82.3k tokens) and now answers wrongly**: "Top results: Open-Meteo wind forecast: precipitation 0, precipitation probability 0" instead of "Vienna is warmer by 3.3 °C". After-r2 answered correctly.
3. **S16-T2 hit the repetition guard** in the judged sample: `resolve_geospatial_location Tokyo, Japan` eight times, run `failed` (`agent_operation_failed`), no map, 13 calls, 62.5k tokens. The probe repeat behaved correctly (Tokyo shown, no false "removed" claim, 3 calls), so it is intermittent (1 of 2).
4. **S03 not fixed**: still city-scale framing (3 `apply_map_plan`, 2 failed render verifications, final map ~10 km wide).
5. **S13** still passes but got worse than after-r2 (12 calls / 92.8k tokens / 2 invalid calls, up from 8 / 50.7k / 2), with a generic "Not completed: …" answer.

Pass count is 12/16 as in after-r2, but the failing set changed (fail: S03, S08, S12, S16; fixed: S02, S06). Obligations 61/67 is the best so far. Firm false successes remain 0, but two completed runs end with a degenerate answer (S08-T2, S12-T4).

## Aggregate delta

| Metric | Baseline | After (`6c954aea`) | After-r2 (`6e3404c8`) | After-r3 (`080cc59a`) | r3 vs r2 |
| --- | --- | --- | --- | --- | --- |
| Scenarios PASS / FAIL | 7 / 9 | 11 / 5 | 12 / 4 (fail: S02 S03 S06 S16) | **12 / 4** (fail: S03 S08 S12 S16) | same count; S02, S06 gained; S08, S12 lost |
| Obligations met / total | 51 / 67 | 58 / 67 | 57 / 67 | **61 / 67 (91%)** | +4 |
| False successes, firm | 3 | 1 | 0 | **0** | held |
| Misleading / degenerate completed answers | 1 | 1 | 2 (S08-T1 wrong place; S16-T2 "layer removed") | **2** (S08-T2 empty answer reported as "work finished"; S12-T4 irrelevant "Top results" as the answer). S08-T1 wrong place and S16 "removed" claim are gone | same count, different cause |
| Invalid tool calls (same counting rule as before) | 6 | 3 | 10 | **4** (S12-T4 1, S13 2, S16-T1 1) | **−6**, target met |
| Redundant provider calls | 1 IMERG + 2 needless `inspect_evidence` | 1 | 1 (S02 MODIS fallback) | **0 identical data repeats**; S06 used two Open-Meteo capabilities (wind + forecast, different datasets); S16-T2 repeated the Tokyo geocode 8× (7 redundant) | S02 fixed; S16-T2 new |
| Unnecessary render attempts | 5 | 1 | 2 | **2** (S03: 3 candidate plans, 2 failed render verifications). S11-T2: both plans absorbed by the no-op gate | same |
| Cross-turn evidence reuse (no new provider call) | 6 of 6 | 6 of 6 | 6 of 6 | **6 of 6** by behaviour, but 2 are hollow: S08-T2 (no answer text), S12-T4 (garbled answer) | quality regression |
| Runs / model-provider 429 | 36 / 9 | 36 / 10 | 26 / 0 | **26 / 0** | environment |
| Slowest run | S07 546 s (cancelled) | S13 57 s | S12-T4 30 s | **S13 42 s** (next S16-T2 30 s, S06 25 s) | n/a |
| Model calls, judged runs | 123 | 109 | 116 | **118** | +2 |
| Tokens, all judged runs | 976k in / 22.8k out | 818k / 19.8k | 871k / 19.4k | **781k / 19.3k** (26 runs, 30.0k avg) | −10% |
| Worst turn (tokens in) | S13 120.5k | S10-T2 140.3k | S02 194.7k | **S13 92.8k** (next S12-T4 82.3k, S09-T2 63.3k, S16-T2 62.5k) | better |

## Targeted items

| Item | Result | Evidence |
| --- | --- | --- |
| **S02** Lugano vs Milan | **FIXED** (sample; the rate-limit path was not exercised) | PASS 5/5. 7 calls, 51.7k tokens, 0 invalid. Two point forecasts (10.4 °C vs 10.3 °C), `transform_evidence` difference, answer "Lugano is 0.1 °C warmer", map labels "Lugano 10.4 °C" and "Milan 10.3 °C". No area query, no MODIS fallback. Open-Meteo did not rate-limit this time, so R6's retry/honest-failure branch is unverified live. |
| **S03** Brandenburg Gate | **NOT FIXED** | 2/3. Resolved correctly, centred on the gate with a marker, but the map is city-scale (Tiergarten to Mitte visible), not street level. 3 `apply_map_plan` calls, render verifications 1 and 2 failed, attempt 3 passed at city scale; the R5 small-extent check did not force fine framing, and the answer claims "centered on the gate". |
| **S06** Wellington | **FIXED** | PASS 4/4. Resolved "Wellington, New Zealand" with no clarification (R4 dominant-candidate rule), wind 22.2 km/h + gusts, temperature 15.8 °C, overcast, no map. Caveat: two Open-Meteo capabilities (`openmeteo_pressure_humidity_wind` and `openmeteo_weather_forecast`) were described and executed, not one; no identical repeat. 5 calls, 23.9k tokens. |
| **S08-T1** "Earthquakes" as a place | **FIXED** | Only "World" is resolved; answer "The map now shows World … with USGS Earthquakes"; 90 events, 0 invalid calls, 6 calls, 36.6k tokens (after-r2: 1 invalid, wrong place). |
| **S08-T2** (not in the list, new) | **REGRESSED** | Answer "The requested work finished, but the model returned no answer text." after one `inspect_evidence` (statistics view); completion decision `complete / goal_satisfied`. Reproduced in the probe (identical). The strongest event is never named, so O3 fails (3/4). |
| **S10-T2** "World" target | **FIXED** | PASS 5/5. New 24 h query returned 3 events, **one** `apply_map_plan`, no "outside the map view" rejection, no invalid layer reference; the map visibly replaced the 207-event layer with 3 markers. 4 calls, 33.4k tokens (after-r2: 9 calls, 94.2k, 3 plans). Residual: answer text is only "The map now shows World … with USGS Earthquakes" (no count, no "3 events"), and T1 still plots ~25 of 207 without saying so. |
| **S12-T4** | **NOT FIXED, worse** | 82.3k tokens (r2 82.7k). `transform_evidence` still tried to sort on a non-existent `observations.temperature_2m` field; the error now lists the available fields (R6 works as designed) but the model did not recover: the answer is "Top results: Open-Meteo wind forecast: precipitation 0, precipitation probability 0" (twice), no warmer city, no difference. O4 and O6 fail (4/6). T1/T2/T3/T5 were correct (Vienna 9.2 °C, Prague 5.9 °C; T5 maps Prague). |
| **S16-T2** "layer removed" claim | **Claim FIXED, reliability NOT** | In neither sample does the answer claim a radar layer was removed. Judged sample: **repetition loop**, 8× `resolve_geospatial_location Tokyo`, run `failed` (`no_progress`, pending `location_resolved`, `map_candidate_prepared` never cleared), no map. Probe: correct (`apply_map_plan`, "The map now shows Tokyo, Japan on the OpenStreetMap basemap", no data fetch). S16 stays FAIL (2/4: O1 still offers no closest layer, O2 not met in the judged sample). |
| **Invalid tool calls** | **FIXED** (10 → 4) | S12-T4 1, S13 2 (`apply_map_plan` not exposed), S16-T1 1 (coverage explanation, counted as before). S02, S08-T1, S10-T2 now 0. |

## Per-scenario results

Obl = obligations met/total, shown baseline → after → after-r2 → after-r3.

| id | Verdict (base → after → r2 → r3) | Obl | Calls / tokens in·out (r3) | What was observed (r3) |
| --- | --- | --- | --- | --- |
| S01 | PASS → PASS → PASS → **PASS** | 4/4 → 4/4 → 4/4 → 4/4 | 5 / 20.3k·0.7k, 13 s | 7.5 °C for Zurich, one Open-Meteo call, "No map created, as requested", no map. |
| S02 | FAIL → PASS → FAIL → **PASS** | 4/5 → 5/5 → 1/5 → **5/5** | 7 / 51.7k·1.4k | See targeted items. |
| S03 | FAIL → FAIL → FAIL → **FAIL** | 1/3 → 1/3 → 2/3 → **2/3** | 5 / 24.2k·0.5k | City-scale framing, 2 failed render verifications before the pass. |
| S04 | PASS → PASS → PASS → **PASS** | 3/3 each | 2 / 5.8k·0.1k | Rome, metro-scale view, 2 calls, no provider. |
| S05 | PASS → PASS → PASS → **PASS** | 4/4 each | T1 1 / 2.8k·0.1k; T2 4 / 15.4k·0.4k | T1 asks Illinois vs Massachusetts (Springfield still clarifies after R4); T2 maps Springfield, MA. |
| S06 | FAIL → FAIL → FAIL → **PASS** | 1/4 → 1/4 → 1/4 → **4/4** | 5 / 23.9k·1.2k, 25 s | See targeted items. |
| S07 | FAIL → PASS → PASS → **PASS** | 1/4 → 4/4 → 4/4 → 4/4 | 5 / 27.1k·0.8k, 21 s | One USGS `valid_empty`, no map, no invalid calls; the answer is terse ("returned no matching data … Not delivered: the requested map") and does not explain that M15 is out of range. |
| S08 | FAIL → PASS → PASS → **FAIL** | 3/4 → 4/4 → 4/4 → **3/4** | T1 6 / 36.6k·1.3k; T2 3 / 22.0k·0.3k | T1 fixed; T2 returns no answer text. No new USGS call, no re-render (reuse held). |
| S09 | PASS → PASS → PASS → **PASS** | 5/5 each | T1 5 / 28.6k·1.2k; T2 4 / 63.3k·1.2k | Three cities resolved once, T2 precipitation for all three, values given. T2 token cost is up (47.4k → 63.3k) because the model issued an extra describe plus three executes. |
| S10 | PASS → PASS → PASS → **PASS** | 5/5 each | T1 6 / 32.6k·0.9k; T2 4 / 33.4k·1.0k | Stale-map caveat is gone: 3 markers after T2. |
| S11 | FAIL → PASS → PASS → **PASS** | 3/4 → 4/4 → 4/4 → 4/4 | T1 2 / 5.8k; T2 2 / 11.8k | T2: both plans absorbed by the no-op gate ("nothing was re-rendered"); answer says the map was already showing Lisbon. |
| S12 | PASS → PASS → PASS → **FAIL** | 6/6 → 6/6 → 6/6 → **4/6** | T1 2 / 5.9k; T2 4 / 27.5k; T3 4 / 36.8k; T4 6 / 82.3k; T5 3 / 39.8k (total 192.3k) | T4 fails (see targeted items). T3 correctly fetched only Prague. |
| S13 | FAIL → FAIL → PASS → **PASS** | 3/5 → 4/5 → 5/5 → **5/5** | 12 / 92.8k·2.6k, 42 s (r2 8 / 50.7k) | Portugal resolved, MODIS raster described and fetched, two `apply_map_plan` "not exposed" invalid calls, run ends `failed`, map blank, nothing invented. Answer is a generic "Results gathered so far … Not completed: …" ending "Only map imagery layers were available … carry no numeric values, so the requested wildfire hotspots could not be computed". Honest but clumsy, and no longer offers the imagery layer. |
| S14 | PASS each | 3/3 each | 2 / 5.3k·0.1k | Haiku, no tools. |
| S15 | FAIL → FAIL → PASS → **PASS** | 3/4 → 3/4 → 4/4 → 4/4 | 3 / 9.9k·0.4k | "Identified place: Lugano, Ticino, Switzerland"; the odd "already showing" opening from r2 is gone. |
| S16 | FAIL → FAIL → FAIL → **FAIL** | 2/4 each | T1 3 / 12.8k·0.4k; T2 13 / 62.5k·1.6k | T1 same readable coverage explanation. T2 judged sample loops (see targeted items); probe passes. |

## Regressions against after-r2 (plain list)

Causes are hypotheses from run events; nothing was changed to test them.

1. **S08-T2 empty answer** (reproduced 2 of 2). The loop finalised with `goal_satisfied` and substituted a generic message when the model returned no text after `inspect_evidence`. The completion gate accepts an empty model answer as success; before, the model produced text from the same tool result. Suspect: the changed `inspect_evidence`/execute summaries (R6 `record_fields`) or finalisation path.
2. **S12-T4 wrong final answer.** After the failed sort the model answered from an unrelated evidence summary ("wind forecast: precipitation 0"), i.e. the final text does not match the question. The completion gate did not check that the answer addresses the question or the requested comparison.
3. **S16-T2 repetition loop (intermittent).** `location_resolved` stayed pending after eight successful Tokyo resolutions; the model never reached `apply_map_plan`. Suspect: R5's superseded-layer / "unsupported layer removal" logic or a follow-up that references the earlier turn's (failed) radar target keeps the requirement unsatisfied.
4. **S13 slightly worse** (12 vs 8 calls, 92.8k vs 50.7k tokens, answer no longer offers the imagery layer); **S09-T2 +16k tokens**.

## What R4–R6 demonstrably fixed

- **S02** from FAIL to PASS in 7 calls, point queries, labelled map.
- **S06** Wellington resolved as dominant, Springfield still clarifies (R4).
- **S08-T1** "Earthquakes" no longer treated as a place (R4); 0 invalid calls.
- **S10-T2** the "World" out-of-view rejection and invalid layer reference are gone (R5), map updated, 94k → 33k tokens.
- **S16 "layer removed" claim** no longer made (R5).
- **Invalid tool calls** 10 → 4; transform errors now list available fields (R6, visible in S12-T4).
- Not verified live: R6 provider rate-limit/timeout recovery (no rate limit occurred).

## Remaining failures, most important first

1. **S08-T2** empty answer accepted as success (reproducible).
2. **S12-T4** irrelevant final answer and 82k-token comparison turn.
3. **S16-T2** intermittent repetition loop with pending `location_resolved`.
4. **S03** landmark framing still city-scale although the render check now runs twice.
5. **S13** noisy generic answer, 2 `apply_map_plan` "not exposed" invalid calls, 93k tokens.
6. **S10 / S08-T1** disclosure gaps: ~25 of 90/207 events plotted without saying so; S07 answer does not explain the M15 range.
