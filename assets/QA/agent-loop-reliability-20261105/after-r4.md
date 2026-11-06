# Agent-loop reliability — AFTER R7–R8 remediation (`develop@a23254e4`, code through `5a49e873`)

- Date: 2026-11-06. Fifth live measurement of the frozen suite. Columns: **baseline** (`b49c699b`, [baseline.md](baseline.md)), **after** (`6c954aea`, [after.md](after.md)), **r2** (`6e3404c8`, [after-r2.md](after-r2.md)), **r3** (`080cc59a`, [after-r3.md](after-r3.md)) and **r4** (this run; R7 `7f9175b4`, R8 `5a49e873`).
- Setup identical to earlier runs: backend from `app/` (`server.app:app`) on 5002, **no `--reload`**, `FASTAPI_PORT=5002 UI_PORT=5000`, `ng serve` on 5000, built-in browser at 1440x900, fresh conversation per scenario, prompts verbatim from [scenarios.md](scenarios.md). Lane OpenCode Go / DeepSeek v4.1 Flash only, verified in the `context_usage` events of every run. HEAD clean apart from the untracked `app/app/`.
- **No model-provider 429, no data-provider rate limit** (26 judged runs, nothing retried). R6's rate-limit path therefore remains unexercised live.
- Raw numbers: [run-metrics-after-r4.txt](run-metrics-after-r4.txt) (26 judged + 5 unjudged probe runs, marked). Screenshots `after-r4-S01.jpg` … `after-r4-S16.jpg` (**S06 included this time**; final UI state; S01 and S06 are text-only and show the transcript pane, S10/S12/S16 show the last turn).
- Verdicts judge answer text + persisted run events + the visible map together, same obligations as the baseline. One sample per scenario; no completed scenario was re-run. After the suite I ran the requested **unjudged probes**: S16 once more (clean) and S08 twice (the first attempt was spoiled: I sent T2 while T1's render acknowledgement was still pending, so T2 was absorbed into T1's run; the second attempt is clean). Probes change no verdict.

## Headline

**S08-T2, S16-T2 and S03 are fixed; S12-T4 is not.** 13/16 scenarios pass (r3 12), obligations 63/67 (best so far), invalid tool calls 6 (r3 4, r2 10), firm false successes 0. But three things got worse or stayed bad:

1. **S12-T4 still returns the irrelevant "Top results: Open-Meteo wind forecast: precipitation 0 …" answer**, identical to r3, at 68.0k tokens. R7's "comparison answers must cite the figures" did not take effect on this path. Vienna 10.0 °C and Prague 6.7 °C were in evidence; the answer never says which is warmer or by how much.
2. **S13 relapsed**: the unrelated IMERG precipitation raster is fetched again (10 calls, 76.3k tokens, 2 invalid calls). The answer is honest ("imagery only … could not be computed") so no false success, but the strict verdict is FAIL (4/5), as in the first after-run.
3. **S09 cost and unrequested maps**: both turns drew a map nobody asked for ("What are today's temperatures…" and "compare precipitation"), and T2 cost **101.5k tokens** (r3 63.3k), now the worst turn of the run.

## Aggregate delta

| Metric | Baseline | After | r2 | r3 | **r4** | r4 vs r3 |
| --- | --- | --- | --- | --- | --- | --- |
| Scenarios PASS / FAIL | 7 / 9 | 11 / 5 | 12 / 4 | 12 / 4 | **13 / 3** (fail: S12, S13, S16) | +1 (S03, S08 gained; S13 lost) |
| Obligations met / total | 51 / 67 | 58 / 67 | 57 / 67 | 61 / 67 | **63 / 67 (94%)** | +2 |
| False successes, firm | 3 | 1 | 0 | 0 | **0** | held |
| Misleading / degenerate completed answers | 1 | 1 | 2 | 2 | **1** (S12-T4 irrelevant answer). S08-T2 empty answer is gone | −1 |
| Invalid tool calls (same counting rule) | 6 | 3 | 10 | 4 | **6** (S02 1, S12-T3 1, S12-T4 1, S13 2, S16-T1 1) | +2 |
| Redundant provider calls | 1 IMERG + 2 | 1 | 1 | 7 (S16-T2 geocode loop) | **1** (S13 unrelated IMERG) | S16 loop gone, S13 back |
| Unnecessary render attempts | 5 | 1 | 2 | 2 | **2** (S09-T1 and S09-T2 unrequested maps); S03 now 1 render; S11-T2 both plans absorbed | same count, different cause |
| Cross-turn reuse (no new provider call) | 6/6 | 6/6 | 6/6 | 6/6, 2 hollow | **6/6**, 1 hollow (S12-T4); S08-T2 now real | better |
| Runs / model-provider 429 | 36 / 9 | 36 / 10 | 26 / 0 | 26 / 0 | **26 / 0** | environment |
| Slowest run | 546 s (cancelled) | 57 s | 30 s | 42 s | **20 s** (S13) | better |
| Model calls, judged runs | 123 | 109 | 116 | 118 | **108** | −10 |
| Tokens, judged runs | 976k / 22.8k | 818k / 19.8k | 871k / 19.4k | 781k / 19.3k | **779k in / 18.3k out** (26 runs, 30.0k avg) | flat |
| Worst turn (tokens in) | S13 120.5k | S10-T2 140.3k | S02 194.7k | S13 92.8k | **S09-T2 101.5k** (next S13 76.3k, S12-T4 68.0k, S02 64.4k) | slightly worse |

## R7 / R8 targets

| Target | Result | Evidence |
| --- | --- | --- |
| **S08-T2** empty answer | **FIXED** | T2 answers from stored evidence: "Strongest event: M6.1 — 144 km SE of Hasaki, Japan (34.9677, 142.1175)", and adds that an M6.1 also occurred in the Fiji region (tie noted, a correct and useful disclosure). One `inspect_evidence`, **no new USGS call**, no re-render, 3 calls, 25.2k tokens. Clean probe repeat: also answers (M6.1 Hasaki, 91 events, mean 4.82). 2 of 2 clean samples answered (r3: 0 of 2). T1 is also fine: 90 events, no wrong place, answer discloses the 7-day window. |
| **S12-T4** analysis answer | **NOT FIXED** | Same failure as r3. `transform_evidence` sort on non-existent `observations.temperature_2m` fails, the error lists fields (R6), the model then derives a 2-record set and answers "Top results: Open-Meteo wind forecast: precipitation 0, precipitation probability 0" (twice). No warmer city, no difference. 67.9k tokens in, 5 calls. The deterministic comparison-figure rule did not intervene; O4 and O6 fail (S12 4/6). T1, T2 (10.0 °C), T3 (6.7 °C, with one invalid `execute_geospatial_capability` retry) and T5 (Prague map) are correct. |
| **S16-T2** repetition loop | **FIXED** | Judged sample: `apply_map_plan` once, "The map now shows Tokyo, Japan on the OpenStreetMap basemap." (no data fetch, no loop, 3 calls, 13.4k tokens, no "radar removed" claim). Clean probe repeat: identical. 2 of 2 (r3: 1 of 2). S16 still FAIL (3/4): T1 explains NOAA radar is US-only but offers no closest alternative layer (O1). |
| **S03** landmark framing | **FIXED** | Resolved "Brandenburg Gate, 1, Pariser Platz, … Berlin", one `apply_map_plan`, one render, 2 calls, 5.9k tokens. The map is framed at street/district level (Tiergarten, Reichstag area and Unter den Linden visible, roughly 2 km across) with the gate near the centre. No marker is drawn (r3 had one) and the answer names the full address but does not say "street level". O1–O3 met (3/3). |
| **Regression check** | **Mixed** | Fixed: S03, S08-T2, S16-T2, S02 and S06 held. New or returned: **S13 IMERG fetch**, **S09 unrequested maps and +38k tokens on T2**, S12-T3 first call invalid (+1). Everything else equal or better. |

## Per-scenario results

Obl = obligations baseline → after → r2 → r3 → r4.

| id | Verdict (base → after → r2 → r3 → **r4**) | Obl | Calls / tokens in·out (r4) | What was observed (r4) |
| --- | --- | --- | --- | --- |
| S01 | PASS ×5 | 4/4 each | 5 / 20.5k·0.7k, 13 s | 7.7 °C for Zurich, one Open-Meteo call, no map. |
| S02 | FAIL → PASS → FAIL → PASS → **PASS** | 4/5 → 5/5 → 1/5 → 5/5 → **5/5** | 8 / 64.4k·1.6k | Two point forecasts (10.5 °C and 10.5 °C), difference 0.0 °C, answer says so, map labelled "Lugano 10.5 °C" and "Milan 10.5 °C". One failed `transform_evidence` sort (wrong field) before the derived record; cost +13k tokens versus r3. |
| S03 | FAIL → FAIL → FAIL → FAIL → **PASS** | 1/3 → 1/3 → 2/3 → 2/3 → **3/3** | 2 / 5.9k·0.2k | See targets. |
| S04 | PASS ×5 | 3/3 | 2 / 5.8k·0.1k | Rome at metro scale, no provider. |
| S05 | PASS ×5 | 4/4 | T1 1 / 2.8k; T2 4 / 15.5k | T1 clarifies IL vs MA; T2 maps Springfield MA with marker. |
| S06 | FAIL ×3 → PASS → **PASS** | 1/4 → 4/4 → **4/4** | 5 / 20.5k·0.9k, 11 s | Wellington NZ resolved without clarification; **one** weather capability (`get_weather_forecast`) described and executed, wind 24 km/h, gusts 51 km/h, 15.9 °C, overcast. Better than r3 (two capabilities). Screenshot shows the text answer and an empty map. |
| S07 | FAIL → PASS → PASS → PASS → **PASS** | 1/4 → 4/4 | 6 / 33.3k·1.0k, 16 s | One USGS `valid_empty`, no map, no fabrication; same terse answer, does not explain the M15 range. |
| S08 | FAIL → PASS → PASS → FAIL → **PASS** | 3/4 → 4/4 → 4/4 → 3/4 → **4/4** | T1 6 / 43.2k·1.4k; T2 3 / 25.2k·0.5k | See targets. T1 plots ~25 of 90 events (title "World"). |
| S09 | PASS ×5 | 5/5 | T1 6 / 44.3k·1.6k; T2 5 / 101.5k·1.7k | Three cities resolved once, three temperatures, T2 precipitation for all three, no temperature refetch. **Defect: both turns added a map nobody asked for**, T2 cost 101.5k tokens (r3 63.3k). Map labels carry the values. |
| S10 | PASS ×4 → **PASS** | 5/5 | T1 7 / 37.3k·1.4k; T2 4 / 34.0k·1.0k | T2 new 24 h query, 3 events, one plan, map shows 3 markers. Answer text is only "The map now shows World …" (no count), as in r3. |
| S11 | FAIL → PASS ×4 | 4/4 | T1 2 / 5.9k; T2 2 / 11.7k | T2: both plans absorbed by the no-op gate; truthful "already centered on Lisbon". |
| S12 | PASS → PASS → PASS → FAIL → **FAIL** | 6/6 → 6/6 → 6/6 → 4/6 → **4/6** | T1 2 / 5.8k; T2 4 / 27.1k; T3 5 / 48.8k; T4 5 / 68.0k; T5 3 / 39.7k (total 189.4k) | T4 fails (see targets). |
| S13 | FAIL → FAIL → PASS → PASS → **FAIL** | 3/5 → 4/5 → 5/5 → 5/5 → **4/5** | 10 / 76.3k·1.2k, 20 s | Portugal resolved, MODIS raster fetched, **IMERG precipitation raster described and fetched (unrelated)**, 2 invalid calls, map blank, answer honest ("matching source is map imagery only … can be shown on the map instead"). A clearer answer than r3, but the unrelated fetch violates O3's "no loop / alternative keyless source only". |
| S14 | PASS ×5 | 3/3 | 2 / 5.3k | Haiku, no tools. |
| S15 | FAIL → FAIL → PASS → PASS → **PASS** | 3/4 → 3/4 → 4/4 | 3 / 9.8k·0.4k | "Identified place: Lugano, Ticino, Switzerland". |
| S16 | FAIL ×4 → **FAIL** | 2/4 ×4 → **3/4** | T1 3 / 12.8k; T2 3 / 13.4k | T2 fixed (O2, O3, O4 met); O1 (closest alternative layer) still unmet. |

## What regressed against r3 (plain list)

1. **S13**: unrelated IMERG fetch back (r2/r3 avoided it), +2 calls and +25k tokens versus r2. The honest answer text improved.
2. **S09**: two unrequested maps, T2 +38k tokens. Hypothesis (unverified): the new presentation rules treat the resolved places as a map-worthy result.
3. **Invalid tool calls 4 → 6**: S02 (+1, failed sort), S12-T3 (+1, retry), S13 same.
4. **S12-T4** not improved (not a new regression).

## Remaining failures, most important first

1. **S12-T4** irrelevant answer to a comparison question (reproduced in r3 and r4; 68k tokens).
2. **S13** unrelated provider fetch plus 2 invalid calls, 76k tokens.
3. **S16** no closest-alternative layer for Tokyo (O1).
4. **S09** unrequested maps and 101k-token T2.
5. Disclosure gaps: ~25 of 90/207 events plotted without saying so (S08/S10), S10-T2 answer has no count, S07 does not explain the M15 range.
