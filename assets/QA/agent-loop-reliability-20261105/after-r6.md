# Agent-loop reliability — AFTER R11 remediation (`develop@cf6447ec`)

- Date: 2026-11-06. Seventh live measurement of the frozen suite. Columns: **baseline** (`b49c699b`, [baseline.md](baseline.md)), **after** (`6c954aea`, [after.md](after.md)), **r2** (`6e3404c8`, [after-r2.md](after-r2.md)), **r3** (`080cc59a`, [after-r3.md](after-r3.md)), **r4** (`a23254e4`, [after-r4.md](after-r4.md)), **r5** (`10678b20`, [after-r5.md](after-r5.md)) and **r6** (this run; R11 `cf6447ec`, final-answer gate false positives).
- Setup identical to earlier runs: backend from `app/` (`server.app:app`) on 5002, **no `--reload`**, `FASTAPI_PORT=5002 UI_PORT=5000`, `ng serve` on 5000, built-in browser at 1440x900, fresh conversation (Start new chat) per scenario, prompts verbatim from [scenarios.md](scenarios.md). Lane OpenCode Go / DeepSeek v4.1 Flash only, verified in the `context_usage` events of every run. HEAD clean apart from the untracked `app/app/`.
- **No model-provider 429, no data-provider rate limit, no contaminated runs**: 26 judged runs, nothing retried (R6 recovery still unexercised live).
- Raw numbers: [run-metrics-after-r6.txt](run-metrics-after-r6.txt) (26 judged + 8 probe runs, marked). Screenshots `after-r6-S01.jpg` … `after-r6-S16.jpg`. Several are cropped to the left ~55% of the map by a viewport glitch of the built-in browser (S01, S02, S06 are text-first by nature); where the crop hides a required element I verified it from the persisted render check instead (S02: `render_observed ready`, `targets_in_view: True`, overlays loaded).
- Verdicts judge answer text + persisted run events + the visible map together. One judged sample per scenario. Unjudged probe repeats after the suite, as requested: **S12 (all five turns), S14, S15, S13**, one each.

## Headline

**R11 fixed what it targeted. 15 of 16 scenarios pass, obligations 66/67, firm false successes 0, tokens the lowest of any run, and none of the r5 fallback-text regressions reproduced in either sample.** The only failing scenario is S16 (no closest-alternative layer), unchanged since the baseline.

- **S14 fixed (2 of 2)**: a proper haiku in the judged run and in the probe.
- **S15 fixed (2 of 2)**: "Identified place: Lugano, Ticino, Switzerland." in the judged run, the probe and the persisted final message (no "Not delivered", no empty value).
- **S12-T5 fixed (2 of 2)**: "The map now shows Prague, Czechia (50.0875, 14.4213) on the OpenStreetMap basemap, centered on the city."; the map is on Prague.
- **S12-T3 and S12-T4 correct in both samples** (judged run and probe): T3 fetched only Prague and compared it with Vienna; T4 answered "Vienna is warmer — by 2.7 °C." from `transform_evidence` with no new provider call. The r5 probe's T3 discovery dead end did not recur. T4 still costs 66.8k (judged) and 52.6k (probe) tokens.

## Aggregate delta

| Metric | Baseline | After | r2 | r3 | r4 | r5 | **r6** | r6 vs r5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Scenarios PASS / FAIL | 7 / 9 | 11 / 5 | 12 / 4 | 12 / 4 | 13 / 3 | 12 / 4 | **15 / 1** (fail: S16) | +3 (S12, S14, S15 gained) |
| Obligations met / total | 51 / 67 | 58 / 67 | 57 / 67 | 61 / 67 | 63 / 67 | 63 / 67 | **66 / 67 (98.5%)** | +3 |
| False successes, firm | 3 | 1 | 0 | 0 | 0 | 0 | **0** | held |
| Misleading / degenerate completed answers | 1 | 1 | 2 | 2 | 1 | 3 | **0** | −3 |
| Invalid tool calls (same counting rule) | 6 | 3 | 10 | 4 | 6 | 4 | **4** (S13 3, S16-T1 1) | same |
| Redundant provider calls | 1 IMERG + 2 | 1 | 1 | 7 | 1 | 0 | **0** | same |
| Unnecessary render attempts | 5 | 1 | 2 | 2 | 2 | 0 | **0** (S03 1 plan; S09 text only; S11-T2 both plans absorbed) | same |
| Cross-turn reuse (no new provider call) | 6/6 | 6/6 | 6/6 | 6/6, 2 hollow | 6/6, 1 hollow | 6/6 | **6/6**, none hollow | held |
| Runs / model-provider 429 | 36 / 9 | 36 / 10 | 26 / 0 | 26 / 0 | 26 / 0 | 26 / 0 | **26 / 0** | environment |
| Slowest run | 546 s (cancelled) | 57 s | 30 s | 42 s | 20 s | 81 s | **35 s** (S13; next S06 23 s) | better |
| Model calls, judged runs | 123 | 109 | 116 | 118 | 108 | 110 | **108** | −2 |
| Tokens, judged runs | 976k / 22.8k | 818k / 19.8k | 871k / 19.4k | 781k / 19.3k | 779k / 18.3k | 742k / 19.4k | **727k in / 19.1k out** (26 runs, 27.9k avg) | −2% |
| Worst turn (tokens in) | S13 120.5k | S10-T2 140.3k | S02 194.7k | S13 92.8k | S09-T2 101.5k | S13 112.6k | **S13 82.5k** (next S12-T4 66.8k, S09-T2 66.6k) | better |

## Targets (R11)

| Target | Result | Evidence |
| --- | --- | --- |
| **S14** haiku replaced by fallback | **FIXED (2 of 2)** | Judged: "Crimson leaves drift down, / frost settles on quiet fields— / autumn breathes goodbye." Probe: a different haiku. 0 tools, no map, no location question, 3 / 2 calls, 8.5k / 5.3k tokens. |
| **S15** empty "Not delivered … at ." | **FIXED (2 of 2)** | Judged and probe: "The map now shows 46.0037, 8.9511 on the OpenStreetMap basemap. Identified place: Lugano, Ticino, Switzerland." matches the reverse geocode in evidence; map centred on Lugano; no unrelated provider. 4 and 3 calls, ~10–13k tokens. |
| **S12-T5** contradictory "Not delivered" | **FIXED (2 of 2)** | Judged: "The map now shows Prague, Czechia (50.0875, 14.4213) … centered on the city." Probe: "The map now shows Prague, Czechia on the OpenStreetMap basemap." One `apply_map_plan`, no contradiction. |
| **S12-T3 / S12-T4** | **Correct in both samples** | **Judged:** T3 7.1 °C Prague, "about 2.7 °C cooler than Vienna", one `get_weather_forecast` (4 calls, 37.3k). T4 "Vienna is warmer — by 2.7 °C" (9.8 − 7.1 = 2.7 ✓), one `transform_evidence`, no provider call (5 calls, 66.8k). **Probe:** T3 7.1 °C Prague (4 calls, 37.6k); T4 "Vienna is warmer — by 2.7 °C" with a ranked table (4 calls, 52.6k). Values match the evidence in both. No discovery dead end, no fallback. |
| **Regression check** | **None found** | Every scenario that passed in r5 passes again with the same or lower cost; S13, S09, S03, S02, S06, S08, S10, S11, S16-T2 held (details below). |

## Per-scenario results

Obl = obligations baseline → after → r2 → r3 → r4 → r5 → r6.

| id | Verdict (base → after → r2 → r3 → r4 → r5 → **r6**) | Obl (r5 → **r6**) | Calls / tokens in·out (r6) | What was observed (r6) |
| --- | --- | --- | --- | --- |
| S01 | PASS ×7 | 4/4 | 5 / 20.4k·0.7k, 9 s | 7.9 °C for Zurich, one Open-Meteo call, "just the number" with context, no map. |
| S02 | FAIL → PASS → FAIL → PASS → PASS → PASS → **PASS** | 5/5 | 7 / 52.1k·1.5k | Milan 10.7 °C vs Lugano 10.5 °C, "Milan is 0.2 °C warmer"; labelled map with both cities (render verified, both targets in view); 0 invalid calls. |
| S03 | FAIL ×4 → PASS ×3 | 3/3 | 2 / 5.9k·0.2k | Street-level framing at Pariser Platz, one plan. |
| S04 | PASS ×7 | 3/3 | 2 / 5.8k·0.1k | Rome at metro scale, no provider. |
| S05 | PASS ×7 | 4/4 | T1 1 / 2.8k; T2 4 / 15.5k | T1 clarifies IL vs MA; T2 maps Springfield MA. |
| S06 | FAIL ×3 → PASS ×4 | 4/4 | 8 / 49.1k·2.3k, 23 s | Wellington NZ without clarification; 24.2 km/h wind, gusts 50.4 km/h, 16.0 °C overcast. Two Open-Meteo capabilities (wind, forecast) as in r3/r5; the stray "Not completed" line of r5 is gone. |
| S07 | FAIL → PASS ×5 | 4/4 | 5 / 26.7k·0.8k | One USGS `valid_empty`, no map, same terse answer (does not explain the M15 range). |
| S08 | FAIL → PASS → PASS → FAIL → PASS → PASS → **PASS** | 4/4 | T1 5 / 32.9k·1.0k; T2 3 / 23.3k·0.5k | T2 names M6.1, 144 km SE of Hasaki, Japan, notes the equal M6.1 in the Fiji region, from one `inspect_evidence`, no new USGS call, no re-render. |
| S09 | PASS ×7 | 5/5 | T1 5 / 28.8k·1.4k; T2 4 / 66.6k·1.3k | Text-only both turns (no unrequested maps), three temperatures, then precipitation for all three, no temperature refetch. T2 cost unchanged from r5 (66.9k). |
| S10 | PASS ×7 | 5/5 | T1 7 / 37.6k·1.3k; T2 4 / 34.2k·0.9k | T2 new 24 h query, 3 events, map shows the 3 markers; answer still only "The map now shows World …" (no count). |
| S11 | FAIL → PASS ×6 | 4/4 | T1 2 / 5.8k; T2 2 / 11.8k | T2 both plans absorbed, truthful "already showing Lisbon". |
| S12 | PASS ×3 → FAIL → FAIL → FAIL → **PASS** | 5/6 → **6/6** | T1 2 / 5.8k; T2 4 / 27.6k; T3 4 / 37.3k; T4 5 / 66.8k; T5 3 / 40.2k (total 177.6k; r5 177.3k) | See targets. |
| S13 | FAIL → FAIL → PASS → PASS → FAIL → PASS → **PASS** | 5/5 | 11 / 82.5k·2.1k, 35 s (r5 13 / 112.6k, 81 s) | No IMERG; MODIS fetched; honest "map imagery only … the imagery layer can be shown on the map instead"; map blank; 3 invalid calls (2× `apply_map_plan` not exposed, 1× imagery-only transform). Probe: 8 calls / 55.1k / 13 s, same answer, 2 invalid calls. |
| S14 | PASS ×5 → FAIL → **PASS** | 2/3 → **3/3** | 3 / 8.5k·0.3k | See targets. |
| S15 | FAIL → FAIL → PASS ×3 → FAIL → **PASS** | 3/4 → **4/4** | 4 / 12.8k·0.5k | See targets. |
| S16 | FAIL ×6 → **FAIL** | 3/4 | T1 3 / 12.8k; T2 3 / 12.8k | T1: "NOAA Radar only covers United States … Which other data should I show there?"; T2: Tokyo shown, no overlay, no new data, no "removed" claim (O2, O3, O4 met). O1 still unmet: no closest alternative layer shown or named. |

## Regressions against r5

None observed. Items to keep an eye on that did not change: S13 still has 2–3 invalid `apply_map_plan`/imagery-transform calls and is the most expensive turn (82.5k judged, 55.1k probe); S12-T4 is correct but costs 52–67k tokens for a comparison that needs one stored-evidence transform; S06 still uses two Open-Meteo capabilities for one question.

## Remaining failures and gaps, most important first

1. **S16 O1**: no closest-alternative layer for Tokyo after the radar coverage rejection (open since the baseline).
2. **S13 cost and invalid calls**: 3 invalid calls and 82.5k tokens in the judged run for a "not available" answer.
3. **S12-T4 / S09-T2 / S06 token cost** (66.8k, 66.6k, 49.1k).
4. Disclosure gaps: ~25 of 91/207 events are plotted without saying so (S08/S10), the S10-T2 answer has no count, S07 does not explain the M15 range.
5. Environment caveat: no rate limit occurred in any run, so R6's rate-limit recovery is still not verified live.
