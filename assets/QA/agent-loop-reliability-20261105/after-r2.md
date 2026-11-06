# Agent-loop reliability — AFTER R1–R3 remediation (`develop@6e3404c8`)

- Date: 2026-11-06. Third live measurement of the frozen suite. Columns throughout: **baseline** (`b49c699b`, [baseline.md](baseline.md)), **after** (`6c954aea`, [after.md](after.md)) and **after-r2** (`6e3404c8`, this run; remediation `d750bb50` R1, `0d0d8ed7` R2, `6e3404c8` R3).
- Setup identical to the earlier runs: backend from `app/` (`server.app:app`) on 5002, **no `--reload`**, `FASTAPI_PORT=5002 UI_PORT=5000`, UI by `ng serve --port 5000`, built-in browser at 1440x900, fresh conversation per scenario, prompts verbatim from [scenarios.md](scenarios.md). Lane: OpenCode Go / DeepSeek v4.1 Flash only, verified in the `context_usage` events of all 26 runs. HEAD was clean apart from the untracked `app/app/`.
- This round had **no model-provider 429** (26 runs, all judged, nothing retried). One provider-side rate limit occurred on the keyless data source (Open-Meteo, S02, see below).
- Raw per-run numbers: [run-metrics-after-r2.txt](run-metrics-after-r2.txt). Screenshots: `after-r2-S01.jpg` … `after-r2-S16.jpg` (final UI state; S10, S12, S16 show the last turn).
- Verdicts judge answer text + persisted run events/evidence + the visible map together, with the same obligations and rules as the baseline. Each scenario was run once; I did not re-run any scenario that completed (protocol), so single-sample variance applies to every row.

## Headline

R1 delivered what it targeted (S15 fixed, S16 much improved) and R3 fixed the Brandenburg Gate clarification and made S13 cheap and honest, but the run **regressed on four fronts against the first after-run**: **S02 flipped PASS→FAIL** (1/5 obligations, 17 calls, 195k tokens), **invalid tool calls rose from 3 to 10**, **S08-T1 now mislabels the place** ("Earthquakes, Waitaki District, Canterbury, New Zealand"), and **the S10-T2 "requested places outside the map view: World" failure that R2 targeted is unchanged**. Firm false successes are 0 for the first time (target met), pass count is 12/16, obligations are 57/67 (one fewer than after).

## Aggregate delta

| Metric | Baseline | After (`6c954aea`) | After-r2 (`6e3404c8`) | r2 vs after |
| --- | --- | --- | --- | --- |
| Scenarios PASS / FAIL | 7 / 9 | 11 / 5 | **12 / 4** (fail: S02 S03 S06 S16) | +1 net (S13, S15 gained; S02 lost) |
| Obligations met / total | 51 / 67 (76%) | 58 / 67 (87%) | **57 / 67 (85%)** | **−1** |
| False successes, firm | 3 (S02, S13, S15) | 1 (S15) | **0** | −1, **target 0 met** |
| False/misleading statements, partial | 1 (S08-T1) | 1 (S10-T1) | **2** (S08-T1 names a wrong place; S16-T2 says a radar layer "has been removed" that never existed) | +1 |
| Invalid tool calls (clarifications excluded; S16-T1 coverage rejection counted as in earlier runs) | 6 | 3 | **10** (S02 4, S08-T1 1, S10-T2 1, S12-T4 1, S13 2, S16-T1 1) | **+7 regression** |
| Redundant provider calls | 1 unrelated IMERG + 2 needless `inspect_evidence` | 1 (S13 IMERG) | **1** (S02 MODIS raster fallback for a numeric ask); S13 IMERG gone | unchanged count, S13 fixed |
| Unnecessary render attempts | 5 | 1 | **2** (S02 retry after a failed verification; S10-T2 second candidate). S11-T2: no-op gate, 0 renders | +1 |
| Cross-turn evidence reuse | 6 of 6 | 6 of 6 | **6 of 6** (S08-T2 no USGS call; S09-T2 no re-resolve, no temperature refetch; S11-T2 no geocode; S12-T3/T4/T5) | unchanged |
| Runs / model-provider 429 | 36 / 9 (25%) | 36 / 10 (28%) | **26 / 0 (0%)** | environment, not code |
| Wall time | typical 2–23 s; S13 52 s; S07 546 s (cancelled) | typical 2–30 s; S13 57 s, S02 52 s | **1–30 s** (slowest S12-T4 30 s); no stall | better |
| Model calls, judged runs | 123 | 109 | **116** | +7 (S02 +10, S12 +3, S08 +1, minus S13 −6) |
| Tokens, all runs | 976k in / 22.8k out (36 runs, 27 judged: 36.1k avg) | 818k / 19.8k (36 runs, 26 judged: 31.5k avg) | **871k / 19.4k (26 runs: 33.5k avg)** | +6% avg per judged run; S02 alone is 195k (22% of the total) |
| Worst turn (tokens in) | S13 120.5k | S10-T2 140.3k | **S02 194.7k** (next: S10-T2 94.2k, S12-T4 82.7k) | worse |

Per-turn token highlights (baseline → after → r2): S13 120.5k → 121.8k → **50.7k**; S08-T2 18.8k → 45.4k → **23.9k**; S10-T2 67.8k → 140.3k → **94.2k**; S12-T4 69.0k → 56.3k → **82.7k**; S12 total 178k → 162k → **204k**; S02 65.8k → 41.8k → **194.7k**; S09-T2 100.8k → 48.2k → 47.4k.

## Per-scenario results

Obl = obligations met/total, shown baseline → after → after-r2. Calls and tokens are for the after-r2 judged runs (the after value is in the notes where it changed materially).

| id | Verdict (base → after → r2) | Obl | Calls / tokens in·out | Delta vs the first after-run and what was observed |
| --- | --- | --- | --- | --- |
| S01 info question, no map | PASS → PASS → **PASS** | 4/4 → 4/4 → 4/4 | 5 / 20.5k·0.7k, 10 s | Unchanged: 6.4 °C for Zurich with window and source, one Open-Meteo call, "No map was created, as requested", no map. |
| S02 Lugano vs Milan | FAIL → PASS → **FAIL** | 4/5 → 5/5 → **1/5** | **17 / 194.7k·3.1k** (after 7 / 41.8k) | **Regression.** The Lugano Open-Meteo call returned a 368-feature grid (area query) instead of one point; the Milan point forecast failed with "The provider rate limit was reached" (keyless provider capacity, environmental); the run then fell back to a MODIS land-surface-temperature raster, with 4 invalid calls (2 `apply_map_plan` semantic validation, 1 `not exposed`, 1 provider rate limit) and 2 render attempts (first failed verification). The answer is honest ("I can't state a Lugano-vs-Milan difference… Milan has no numeric reading"; "The map layer shows only 5 of 368 records") so it is not a false success, but O2–O5 fail: no temperature for Milan, no difference, no labelled values on the map. |
| S03 Brandenburg Gate | FAIL → FAIL → **FAIL** | 1/3 → 1/3 → **2/3** | 2 / 5.9k·0.2k | **R3 effect:** no clarification any more; resolved as `Brandenburg Gate, 1, Pariser Platz, … Berlin` and mapped (O1, O3 met). **O2 fails:** the map is framed at city scale (Charlottenburg to Friedrichshain, roughly 12 km across), not street level at Pariser Platz. |
| S04 Rome | PASS → PASS → **PASS** | 3/3 → 3/3 → 3/3 | 2 / 5.8k·0.2k | Unchanged (call count back to 2). |
| S05 Springfield → Massachusetts | PASS → PASS → **PASS** | 4/4 → 4/4 → 4/4 | 5 / 18.3k·0.5k | Springfield still clarifies (IL/MA) as required; T2 maps Springfield MA. R3 did not break the must-clarify case. |
| S06 ambiguous tool (Wellington) | FAIL → FAIL → **FAIL** | 1/4 → 1/4 → 1/4 | 2 / 6.5k·0.4k | **R3 target not reached:** Wellington (NZ vs Texas) still ends in a clarification, so the tool-choice behaviour is never exercised. |
| S07 impossible magnitude | FAIL → PASS → **PASS** | 1/4 → 4/4 → 4/4 | 5 / 26.9k·0.9k, 17 s | Unchanged: one USGS `valid_empty`, no map plan, no invalid calls, honest terse answer. |
| S08 earthquakes → strongest | FAIL → PASS → **PASS** | 3/4 → 4/4 → 4/4 | T1 9 / 52.2k·1.6k; T2 3 / 23.9k·0.4k (after 6+5 / 43.1k+45.4k) | T2: **R2 effect**, one `inspect_evidence` (statistics view), no new USGS call, M6.1 Fiji region, no re-render, 23.9k tokens (was 45.4k). **T1 regression:** the resolver took "Earthquakes" as a place (`Resolved Earthquakes, Waitaki District, Canterbury, New Zealand`) as well as "World"; the map title and the answer ("The map now shows Earthquakes, Waitaki District, Canterbury, New Zealand on the OpenStreetMap basemap with USGS Earthquakes") name that wrong place; 1 invalid call (`execute_geospatial_capability` semantic validation); the answer no longer reports counts or that only part of the 92 events is on the map. Markers are visible, so O1 holds. |
| S09 temperatures → precipitation | PASS → PASS → **PASS** | 5/5 → 5/5 → 5/5 | T1 5 / 28.7k·1.3k; T2 3 / 47.4k·1.1k | Unchanged: text-only T1, places reused, three precipitation fetches, no temperature refetch. |
| S10 30 days → 24 h | PASS → PASS → **PASS** (same stale-map caveat) | 5/5 → 5/5 → 5/5 | T1 6 / 32.5k·1.1k; T2 9 / 94.2k·2.4k (after 7+10 / 56.2k+140.3k) | T1: 205 events, **no invalid call and no false count claim any more** (answer is only "The map now shows World on the OpenStreetMap basemap with USGS Earthquakes"; it does not disclose that the map holds ~25 of 205 markers). T2: new 24 h query (2 features), but **the map was still not updated: the same "Presentation contract failed: requested places outside the map view: World" message**, plus one invalid `apply_map_plan` ("Layer … is not in the active map"), 3 `apply_map_plan` calls, and the answer is now only "returned 2 feature(s)" with no event list. Cost down 33% vs after but still 1.4× the baseline. Scored under the baseline's stale-layer leniency; **the R2 objective for this turn is not met.** |
| S11 unchanged map re-request | FAIL → PASS → **PASS** | 3/4 → 4/4 → 4/4 | T1 2 / 5.9k; T2 2 / 11.7k | T2: both `apply_map_plan` calls absorbed by the no-op gate, no geocode, no render; the answer now says "already centered on Lisbon… no changes were needed" (better wording than after). |
| S12 long conversation | PASS → PASS → **PASS** | 6/6 → 6/6 → 6/6 | 20 / 204.5k·3.0k (after 17 / 162.2k; T4 82.7k vs 56.3k) | All answers correct (Vienna 5.4 °C, Prague 2.5 °C, "Vienna is warmer — by 2.9 °C", Prague map names Prague and verifies the render). **Cost regression:** T4 used `transform_evidence` (one failed sort on a wrong field name) before answering, 82.7k tokens; T3 48.5k (was 36.1k). No 429 this time. |
| S13 wildfire hotspots Portugal | FAIL → FAIL → **PASS** | 3/5 → 4/5 → **5/5** | 8 / 50.7k·1.1k, 13 s (after 14 / 121.8k, 57 s) | **R3 effect:** no unrelated IMERG fetch, no loop; one raster descriptor inspected, answer: "The matching source is map imagery only: it has no point or numeric records, so the requested values could not be computed. The imagery layer can be shown on the map instead." Map left blank, nothing invented. 2 invalid calls remain (`apply_map_plan` not exposed for the step; `transform_evidence` on a raster, now with a user-facing explanation). Caveat: it offers the imagery layer instead of showing it. |
| S14 haiku | PASS → PASS → **PASS** | 3/3 → 3/3 → 3/3 | 2 / 5.3k·0.1k | Unchanged. |
| S15 numeric coordinates | FAIL → FAIL → **PASS** | 3/4 → 3/4 → **4/4** | 3 / 9.9k·0.5k | **R1 effect:** "46.0037, 8.9511 resolves to Lugano, Ticino, Switzerland (confidence: high)", map centred on Lugano, no unrelated provider. Firm false success gone. Minor: the answer opens with "The map is already showing that point", which is odd for a fresh conversation. |
| S16 radar then clear | FAIL → FAIL → **FAIL** | 2/4 → 2/4 → 2/4 | T1 3 / 12.6k·0.4k; T2 3 / 12.8k·0.3k (after 3+1) | **R1 effects:** T1 is now a clear user-facing explanation ("NOAA Radar only covers United States… No other source shortlisted… covers Tokyo, Japan. Which other data should I show there?") instead of the raw policy string, and T2 now **shows Tokyo** with no overlay and no new data call (O2, O3 met). Still failing by a strict reading: O1 expects "the closest available layer" (none is shown or named) and O4 requires truthful layer state, but T2 says "The radar layer has been removed" although none was ever added. A lenient reading of O1 would give 3/4, still a fail. |

## Regressions against the first after-run (plain list)

Cause hypotheses are inferred from run events and code reading; nothing was changed to test them.

1. **S02 PASS → FAIL (1/5, 17 calls, 195k tokens, 4 invalid calls).** Two contributing factors seen in the events: the Lugano forecast was issued as an area query (368 grid features, "map layer shows only 5 of 368 records") and the Milan point forecast hit a provider rate limit; the loop then pivoted to an unrelated MODIS raster instead of retrying Open-Meteo once for Milan or asking the user. The environmental half (Open-Meteo capacity) cannot be attributed to R1–R3, but the point-vs-area argument choice and the unbounded recovery are agent-loop behaviour. This is one sample; the first after-run passed with 7 calls on the same prompt.
2. **Invalid tool calls 3 → 10.** New sources: S02 (4), S08-T1 (semantic validation on `execute_geospatial_capability`), S10-T2 (`apply_map_plan` referencing a layer not in the active map — probably a side effect of R2's "superseded layers replaced rather than stacked": the model addresses the new evidence layer before the old one is replaced), S12-T4 (`transform_evidence` sort on a non-existent field).
3. **S08-T1 wrong place label.** The route/resolver treats the subject word "Earthquakes" as a place, resolves it to a Waitaki District feature, and the final answer and map title repeat it. Hypothesis: a side effect of R3's acceptance of dominant place candidates (a single strong geocoder hit for a non-place token is now accepted instead of being rejected or clarified); the "shortlist pruned by subject terms" change addresses capabilities, not the location query. Area: location extraction in `route_request` and `resolve_geospatial_location` candidate acceptance.
4. **S10-T2 presentation contract unchanged.** The same finding string appears; `PresentationContract.view_findings` (`app/server/domain/agent/presentation_contract.py`) still rejects a global ("World") target after the render. The R2 change evidently does not cover this path (the target is created by the `resolve_geospatial_location` "World" call, which this round also made in S08-T1 and S10-T1). The old 30-day layer remains on the map and the answer is shorter than before.
5. **S12-T4 and S12-T3 cost (+27% for the scenario).** The comparison turn now spends 82.7k tokens on `transform_evidence` plus `inspect_evidence`; the ranked-view change of R2 helped S08-T2 but not this path.
6. **S16-T2 untruthful layer statement** ("radar layer has been removed") is new wording introduced by the R1 "known place after a failed layer" route.

## Remaining failures and open items

- **S02:** not reliable (1 pass, 1 fail in two runs); needs bounded recovery after a data-source rate limit and a point query for city comparisons.
- **S03:** place resolved correctly but the view is city-wide; the fine-location framing check (`FINE_LOCATION_TYPES` / `MAX_FINE_VIEW_SPAN_DEGREES` in the presentation contract) did not engage for this landmark.
- **S06:** Wellington still clarifies; the R3 dominant-candidate rule did not fire for NZ vs Texas (Springfield correctly still clarifies).
- **S10-T2:** map not updated, "World" target rejected, invalid layer reference.
- **S16:** no nearest alternative layer for Tokyo; "removed" claim.
- **S08-T1:** wrong place label; **S13:** blank map although an imagery layer exists and was offered.
- Full run counters: 26 runs, 12 PASS scenarios, 0 firm false successes, 10 invalid calls, 0 model-provider 429.

## What the remediation demonstrably fixed

- **S15** (R1): coordinate identification with reverse geocode, answer names Lugano.
- **S16-T1/T2** (R1): readable coverage explanation, known place after a failed layer turn goes to a map; remaining defects above.
- **S03 clarification** (R3): Brandenburg Gate resolved without clarification (framing still wrong).
- **S13** (R3): from 14 calls / 122k tokens / unrelated provider fetch to 8 calls / 51k tokens, concise honest answer.
- **S08-T2** (R2): 45.4k → 23.9k tokens, single `inspect_evidence`.
- **S10-T1** (R2): no invalid call, no false "all 205 on the map" claim (the truncation is no longer disclosed either).
- Model-provider 429s: none this round (environmental, not attributable).
