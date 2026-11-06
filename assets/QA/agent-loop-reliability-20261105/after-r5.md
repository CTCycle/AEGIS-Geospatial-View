# Agent-loop reliability — AFTER R9–R10 remediation (`develop@10678b20`)

- Date: 2026-11-06. Sixth live measurement of the frozen suite. Columns: **baseline** (`b49c699b`, [baseline.md](baseline.md)), **after** (`6c954aea`, [after.md](after.md)), **r2** (`6e3404c8`, [after-r2.md](after-r2.md)), **r3** (`080cc59a`, [after-r3.md](after-r3.md)), **r4** (`a23254e4`, [after-r4.md](after-r4.md)) and **r5** (this run; R10 `2da9a2fa`, R9 `10678b20`).
- Setup identical to earlier runs: backend from `app/` (`server.app:app`) on 5002, **no `--reload`**, `FASTAPI_PORT=5002 UI_PORT=5000`, `ng serve` on 5000, built-in browser at 1440x900, fresh conversation per scenario, prompts verbatim from [scenarios.md](scenarios.md). Lane OpenCode Go / DeepSeek v4.1 Flash only, verified in the `context_usage` events of every run. HEAD clean apart from the untracked `app/app/`.
- **No model-provider 429 and no data-provider rate limit** in 26 judged runs, nothing retried (R6 recovery still unexercised live).
- One procedural slip, disclosed: after the first page load the UI restored the previous (r4 probe) conversation, so my first S01 message landed in an old chat. That run is marked CONTAMINATED in the metrics file and is **not judged**; S01 was redone in a fresh chat and that run is the judged one.
- Raw numbers: [run-metrics-after-r5.txt](run-metrics-after-r5.txt) (1 contaminated + 26 judged + 7 probe runs, marked). Screenshots `after-r5-S01.jpg` … `after-r5-S16.jpg` (all 16; final UI state; S02 is cropped to the left half by a viewport glitch, so I verified Milan's label from the persisted render check instead: `targets_in_view: True`, overlays loaded).
- Verdicts judge answer text + persisted run events + the visible map together. One judged sample per scenario. After the suite I took **unjudged probes**: S12 (T1–T4), S13, and — because they regressed — S14 and S15, one repeat each.

## Headline

**S13 and S09 are fixed; S12-T4 is fixed on the judged run but not reliably; and R9/R10 introduced a new class of failure: valid answers replaced by a fallback.** 12/16 pass (r4 13), obligations 63/67 (same as r4), firm false successes 0, invalid tool calls 4 (r4 6), tokens 742k (best of all runs).

1. **S12-T4 fixed (judged run)**: "Vienna is warmer — by 2.9 °C" (9.9 vs 7.0 °C), no new provider call, 66.4k tokens. **Probe repeat failed**: T3 ("And in Prague?") ended "No supported capability matched the request after discovery" after four empty `discover_geospatial_capabilities` calls, and T4 then answered "The model's answer did not match the verified results" at 95.3k tokens. So 1 of 2 samples.
2. **S13 fixed (IMERG gone)**: no unrelated provider fetch in either sample. But the judged run burned 13 calls, **112.6k tokens, 81 s and 3 invalid `apply_map_plan` calls** (the worst turn of the whole run); the probe was 9 calls / 67k.
3. **S09 fixed**: no unrequested maps on either turn (r4: both), T2 66.9k tokens (r4 101.5k, r3 63.3k).
4. **New failures, all intermittent:**
   - **S14** (haiku): the answer became "The model's answer did not match the verified results." — no haiku delivered (probe: fine).
   - **S15**: answer "The map now shows 46.0037, 8.9511 … Not delivered: the name of the place at ." — Lugano not named although `resolve_geospatial_location` returned it, and the sentence is a broken template with an empty value (probe: fine).
   - **S12-T5**: the map is on Prague and render-verified, but the answer says "Not delivered: the place Prague, Czechia."

## Aggregate delta

| Metric | Baseline | After | r2 | r3 | r4 | **r5** | r5 vs r4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Scenarios PASS / FAIL | 7 / 9 | 11 / 5 | 12 / 4 | 12 / 4 | 13 / 3 | **12 / 4** (fail: S12, S14, S15, S16) | −1 (S13 gained; S12 stays; S14, S15 lost) |
| Obligations met / total | 51 / 67 | 58 / 67 | 57 / 67 | 61 / 67 | 63 / 67 | **63 / 67** | same |
| False successes, firm | 3 | 1 | 0 | 0 | 0 | **0** | held |
| Misleading / degenerate completed answers | 1 | 1 | 2 | 2 | 1 | **3** (S12-T5 "not delivered" with the map on Prague, S14 fallback replaces the haiku, S15 empty-template "Not delivered"); the S12-T4 irrelevant answer is gone | +2, different cause |
| Invalid tool calls | 6 | 3 | 10 | 4 | 6 | **4** (S13 3, S16-T1 1) | −2 |
| Redundant provider calls | 1 IMERG + 2 | 1 | 1 | 7 | 1 | **0** (S13 IMERG gone; S06 again used two Open-Meteo capabilities on different datasets, no identical repeat) | −1 |
| Unnecessary render attempts | 5 | 1 | 2 | 2 | 2 | **0** (S09 no maps; S03 1 plan; S11-T2 both plans absorbed) | −2 |
| Cross-turn reuse (no new provider call) | 6/6 | 6/6 | 6/6 | 6/6, 2 hollow | 6/6, 1 hollow | **6/6**, none hollow in the judged run (S08-T2, S09-T2, S11-T2, S12-T3/T4/T5) | better |
| Runs / model-provider 429 | 36 / 9 | 36 / 10 | 26 / 0 | 26 / 0 | 26 / 0 | **26 / 0** | environment |
| Slowest run | 546 s (cancelled) | 57 s | 30 s | 42 s | 20 s | **81 s (S13)** | worse |
| Model calls, judged runs | 123 | 109 | 116 | 118 | 108 | **110** | +2 |
| Tokens, judged runs | 976k / 22.8k | 818k / 19.8k | 871k / 19.4k | 781k / 19.3k | 779k / 18.3k | **742k in / 19.4k out** (26 runs, 28.6k avg) | −5% |
| Worst turn (tokens in) | S13 120.5k | S10-T2 140.3k | S02 194.7k | S13 92.8k | S09-T2 101.5k | **S13 112.6k** (next S09-T2 66.9k, S12-T4 66.4k) | worse |

## R9 / R10 targets

| Target | Result | Evidence |
| --- | --- | --- |
| **S12-T4** comparison answer | **FIXED on the judged run, NOT reliable** | Judged: `transform_evidence` once, no failed sort, "**Vienna is warmer — by 2.9 °C.** Vienna 9.9 °C, Prague 7.0 °C", no new provider call; T3 also said "roughly 3 °C cooler than Vienna". 5 calls, 66.4k tokens (r4 68.0k, so the cost is unchanged). Probe: T3 failed ("No supported capability matched the request after discovery", four `valid_empty` discoveries naming operation `data_retrieval`) and T4 returned the "did not match the verified results" fallback at 95.3k tokens. S12 stays FAIL (5/6): **T5** says "Not delivered: the place Prague, Czechia" while the map shows Prague (render verified, 1 attempt). |
| **S13** unrelated IMERG fetch | **FIXED (2 of 2)** | Judged and probe: only MODIS thermal-anomalies is described/fetched, no IMERG. Judged answer: generic "Results gathered so far … Not completed: …" ending "Only map imagery layers … carry no numeric values …"; probe answer: "The matching source is map imagery only … The imagery layer can be shown on the map instead." Still expensive: judged 13 calls / 112.6k / 81 s with 3 `apply_map_plan` "not exposed" failures; probe 9 calls / 67.1k / 35 s with 2 invalid calls. Map blank, nothing invented. |
| **S09** unrequested maps and T2 cost | **FIXED (maps), cost back to r3 level** | Both turns text-only (0 `apply_map_plan`, `presentation not_required`). T1 28.9k tokens, T2 66.9k (r4 101.5k, r3 63.3k, r2 47.4k). Three temperatures and three precipitation values given, no temperature refetch. |
| **Regression check** | **Regressions** | New: S14 and S15 final answers replaced by fallback text (1 of 2 samples each), S12-T5 contradictory "Not delivered", S12 probe T3 capability-discovery dead end, S13 judged run 112.6k tokens. Fixed earlier and held: S02, S03, S06, S08-T2, S10-T2, S16-T2. |

## Per-scenario results

Obl = obligations baseline → after → r2 → r3 → r4 → r5.

| id | Verdict (base → after → r2 → r3 → r4 → **r5**) | Obl (r4 → **r5**) | Calls / tokens in·out (r5) | What was observed (r5) |
| --- | --- | --- | --- | --- |
| S01 | PASS ×6 | 4/4 → 4/4 | 5 / 22.3k·0.7k, 11 s | 7.8 °C for Zurich, one Open-Meteo call, no map. (First attempt contaminated, redone.) |
| S02 | FAIL → PASS → FAIL → PASS → PASS → **PASS** | 5/5 → 5/5 | 6 / 40.4k·1.5k | Lugano 10.6 °C vs Milan 10.7 °C, "Milan is just 0.1 °C warmer", labelled map with both cities in view, 0 invalid calls (r4 had one failed sort). |
| S03 | FAIL ×4 → PASS → **PASS** | 3/3 → 3/3 | 2 / 5.9k·0.2k | Street-level framing again, one plan, one render. |
| S04 | PASS ×6 | 3/3 | 2 / 5.8k·0.2k | Rome at metro scale. |
| S05 | PASS ×6 | 4/4 | T1 1 / 2.8k; T2 4 / 15.5k | T1 clarifies IL vs MA; T2 maps Springfield MA with marker. |
| S06 | FAIL ×3 → PASS → PASS → **PASS** | 4/4 → 4/4 | 8 / 49.3k·2.3k, 34 s | Resolved NZ, wind 24.8 km/h with gusts 50.4, 16.0 °C overcast. Two Open-Meteo capabilities (wind, forecast) again (r4: one), 34 s and 49k tokens (r4 20k), plus a stray "Not completed: the requested time window was not verified" line. Verdict kept because both obligations hold and nothing was repeated. |
| S07 | FAIL → PASS ×4 → **PASS** | 4/4 | 5 / 24.6k·0.7k | One USGS `valid_empty`, no map, same terse answer. |
| S08 | FAIL → PASS → PASS → FAIL → PASS → **PASS** | 4/4 → 4/4 | T1 6 / 32.8k; T2 4 / 29.3k | T2 names "magnitude 6.1, 144 km SE of Hasaki, Japan" from a single `transform_evidence` (1 record), no new USGS call, no re-render. T1: 91 events, no wrong place. |
| S09 | PASS ×6 | 5/5 | T1 5 / 28.9k·1.4k; T2 4 / 66.9k·1.4k | See targets. |
| S10 | PASS ×5 → **PASS** | 5/5 | T1 6 / 32.6k; T2 4 / 33.6k | T2: new 24 h query, 3 events, one plan, map shows 3 markers. Answer is only "The map now shows World …" (no count). |
| S11 | FAIL → PASS ×5 | 4/4 | T1 2 / 5.9k; T2 2 / 11.8k | T2 both plans absorbed, truthful "already showing this view". |
| S12 | PASS ×3 → FAIL → FAIL → **FAIL** | 4/6 → **5/6** | T1 3 / 8.8k; T2 4 / 26.9k; T3 4 / 36.2k; T4 5 / 66.4k; T5 3 / 39.0k (total 177.3k, r4 189.4k) | T4 correct (target). T5 answer contradicts the map. |
| S13 | FAIL → FAIL → PASS → PASS → FAIL → **PASS** | 4/5 → 5/5 | 13 / 112.6k·2.9k, 81 s | See targets. |
| S14 | PASS ×5 → **FAIL** | 3/3 → **2/3** | 3 / 8.6k·0.3k | O1 broken: the answer is "The model's answer did not match the verified results."; no tools, no map, no location question (O2, O3 hold). Probe repeat: a proper haiku. |
| S15 | FAIL → FAIL → PASS → PASS → PASS → **FAIL** | 4/4 → **3/4** | 3 / 9.6k·0.3k | Coordinates parsed, map centred, no unrelated provider, but the answer ends "Not delivered: the name of the place at ." (Lugano not named). Probe repeat: "Identified place: Lugano, Ticino, Switzerland." |
| S16 | FAIL ×5 → **FAIL** | 3/4 → 3/4 | T1 3 / 12.7k; T2 3 / 12.9k | Unchanged from r4: T2 shows Tokyo with no loop and no "removed" claim; T1 still offers no closest alternative layer (O1). |

## Regressions against r4 (plain list)

Causes are hypotheses from the run events; nothing was changed to test them.

1. **S14 and S15: a correct model answer is replaced by "did not match the verified results" or by a "Not delivered: …" template with an empty value.** Both are single-turn, tool-light scenarios that passed in r2–r4, and each repeated correctly once. This looks like the new comparison/count-claim validation (R9) rejecting answers it should not check (S14 has no tools at all) and the fallback template being rendered with a missing field (S15's empty "at ."). It is the same class as the earlier S12-T4 "Top results" fallback.
2. **S12-T5**: "Not delivered: the place Prague, Czechia" after a verified render of Prague. Same fallback family.
3. **S12 probe T3**: `discover_geospatial_capabilities` demanded the operation `data_retrieval`, found nothing four times, and the turn ended without Prague data; T4 followed with a fallback. One of two S12 samples.
4. **S13 judged run**: 112.6k tokens, 81 s, 3 invalid `apply_map_plan` calls (r4 76k, 20 s, 2).
5. **S06**: 49k tokens, 34 s (r4 20.5k, 11 s), two capabilities again.

## Remaining failures, most important first

1. **Fallback text replacing valid answers** (S14, S15, S12-T5, S12-probe-T4): intermittent, in scenarios that previously passed.
2. **S12 reliability**: T4 correct in 1 of 2 samples; T3 capability-discovery dead end in the probe; T5 contradictory answer.
3. **S13 cost** (112.6k tokens, 81 s, 3 invalid calls) although the IMERG fetch is gone.
4. **S16** no closest-alternative layer for Tokyo (O1).
5. Disclosure gaps: ~25 of 91/207 events plotted without saying so (S08/S10), S10-T2 answer has no count, S07 does not explain the M15 range.
