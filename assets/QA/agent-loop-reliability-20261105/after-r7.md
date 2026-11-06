# Agent-loop reliability — AFTER R12 remediation (`develop@d7d266af` + uncommitted R12)

- Date: 2026-11-06. Eighth live measurement of the frozen suite. Previous run: **r6** (`cf6447ec`, [after-r6.md](after-r6.md)). Remediation notes: [../agent-loop-remediation-20261106/notes.md](../agent-loop-remediation-20261106/notes.md).
- Setup as in earlier runs: backend from `app/` (`server.app:app`, uvicorn, no `--reload`) on 5002, `ng serve` on 5000, built-in browser at 1440x900, fresh conversation per scenario, prompts verbatim from [scenarios.md](scenarios.md). Lane OpenCode Go / DeepSeek v4.1 Flash only, verified in every run's `context_usage` events. No model-provider 429, no data-provider rate limit (R6 recovery still unexercised live).
- Build under test: R12 batches 1–3 plus a `map_layer_counts` lookup fix found during the run. S08-T1 was first run before that fix (`85fd49`, marked PRE-FIX; the backend was restarted and S08 re-run from a fresh chat); S01–S07 do not reach that code path.
- Raw numbers: [run-metrics-after-r7.txt](run-metrics-after-r7.txt). Screenshots `after-r7-S*.jpg` (several are scaled down by the built-in browser pane; verdicts also use persisted render checks).

## Headline

**15 of 16 scenarios pass, obligations 66/67, firm false successes 0, invalid tool calls 1 (r6: 4), tokens −4 %.** The S13 and S06 cost/failure loops are gone and S16-T1 passes for the first time since the baseline. The one judged failure, S16-T2, was a path no earlier run could reach (T1 never drew a layer before); it and an S08-T2 gate false positive were fixed after the suite and **both pass in probes** (PROBE-B), but those fixes have not had a full-suite re-run.

## Aggregate delta

| Metric | r6 | **r7** |
| --- | --- | --- |
| Scenarios PASS / FAIL | 15 / 1 (S16) | **15 / 1** (S16-T2; fixed in probe) |
| Obligations met / total | 66 / 67 | **66 / 67** (S16 O2) |
| False successes, firm | 0 | **0** |
| Misleading / degenerate completed answers | 0 | **1** (S08-T2 correct facts but replaced by the bare fallback; fixed in probe) |
| Invalid tool calls | 4 | **1** (S16-T1 coverage rejection of `noaa_radar`, by design) |
| Redundant provider calls | 0 | **0** |
| Unnecessary render attempts | 0 | **0** |
| Cross-turn reuse | 6/6 | **6/6** |
| Model calls, judged runs | 108 | **107** |
| Tokens, judged runs | 727k in / 19.1k out | **699.5k in / 17.7k out** |
| Worst turn (tokens in) | S13 82.5k | **S09-T2 66.7k** (S12-T4 66.6k) |
| Slowest run | 35 s (S13) | **26 s** (S09-T2) |

## Targets (R12)

| Target | Result | Evidence |
| --- | --- | --- |
| S13 invalid calls, blank map | **FIXED** | 6 calls / 29.5k (r6 11 / 82.5k), 0 invalid calls, MODIS fire imagery layer rendered (`ready`), answer discloses "Only map imagery was available … the imagery is shown instead." |
| S06 no-progress loop | **FIXED** | 5 calls / 23.5k (r6 8 / 49.1k), `goal_satisfied` (r6 ended `insufficient_evidence`); observation time now "06:30 +13:00". |
| S16-T1 closest alternative | **FIXED (3 of 3)** | NOAA rejected for coverage, RainViewer executed and mapped in the same run; judged and second probe state the substitution; first probe (`276f30`) did not, which led to the deterministic substitution disclosure (PROBE-B `f22c3b` names both sources). |
| S08/S10 counts | **FIXED** | S10-T1 "USGS Earthquakes (206 records)", S10-T2 "(1 record)"; S08-T1 model answer "90 events … clustered at low zoom". The "~25 of N" was MapLibre clustering, not a backend cap. |
| S12-T4 cost | **Unchanged** | Correct ("Vienna is warmer — by 1.9 °C", 7.2 − 5.3), one `transform_evidence`, no provider call, still 5 calls / 66.6k. |

## Per-scenario results (judged runs)

| id | Verdict | Obl | Calls / tokens in | Observed |
| --- | --- | --- | --- | --- |
| S01 | PASS | 4/4 | 5 / 20.6k | 7.6 °C Zurich, no map. |
| S02 | PASS | 5/5 | 7 / 52.8k | Lugano 10.6 vs Milan 10.2 °C, "Lugano is 0.4 °C warmer"; labelled map, graduated layer. Answer adds a wrong aside ("different time zones"). |
| S03 | PASS | 3/3 | 2 / 5.9k | Street-level at Pariser Platz. |
| S04 | PASS | 3/3 | 2 / 5.8k | Rome, no provider. |
| S05 | PASS | 4/4 | 1 / 2.9k; 4 / 15.4k | Clarifies IL vs MA; maps Springfield MA. |
| S06 | PASS | 4/4 | 5 / 23.5k | Wellington NZ 20.3 km/h, gusts 45 km/h, 15.9 °C overcast; still two Open-Meteo capabilities (as r6). |
| S07 | PASS | 4/4 | 5 / 24.5k | `valid_empty`, no map; still does not explain the M15 range. |
| S08 | PASS | 4/4 | 7 / 37.4k; 3 / 23.1k | T1 90 events with count. T2 correct (M6.1, 144 km SE of Hasaki) but the model answer was replaced by the bare fallback line: the gate rejected the event latitude "34.9677°" (record coordinates were not accepted). Fixed; PROBE-B `28e8eb` keeps the full answer. |
| S09 | PASS | 5/5 | 5 / 29.0k; 4 / 66.7k | Text only; precipitation for all three without refetching temperatures. |
| S10 | PASS | 5/5 | 6 / 33.7k; 4 / 33.7k | Counts stated both turns; T2 map shows the 1 event. |
| S11 | PASS | 4/4 | 2 / 5.8k; 2 / 11.8k | "already centered on Lisbon". |
| S12 | PASS | 6/6 | 2 / 5.8k; 4 / 27.0k; 4 / 36.6k; 5 / 66.6k; 3 / 39.8k | T4 from stored evidence; T5 Prague shown. |
| S13 | PASS | 5/5 | 6 / 29.5k | See targets. Framing gap: Portugal's Nominatim bbox includes the Azores, so the view spans −32.6° to −5.1° and the mainland sits at the right edge. |
| S14 | PASS | 3/3 | 2 / 5.3k | Haiku. |
| S15 | PASS | 4/4 | 3 / 9.9k | Lugano, Ticino, Switzerland. |
| S16 | **FAIL** | 3/4 | 7 / 39.9k; 7 / 46.7k | T1 passes (see targets). T2: the route kept the layer label "RainViewer Recent Precipitation Radar" as a place target, `location_resolved` never held, only the resolver was exposed (3 calls), `insufficient_evidence`; answer truthful, layer left on. |

## Fixes made after the suite (unit-verified, probed live, no full-suite re-run)

1. `tool_registry.unresolved_route_targets`: a target that spells a layer on the active map is a layer reference, not a place (S16-T2 first cause).
2. `completion.uncovered_map_targets`: the per-target "data layer for each place" rule applies only when the request requires evidence (S16-T2 second cause, found in PROBE-A `6fb728`: "no map layer carries the data for Tokyo, Japan" on a plain framing map).
3. `completion.evidence_coordinates`: record latitudes/longitudes in the run's and earlier turns' evidence count as supported coordinates in the final-answer check (S08-T2).
4. Coverage substitution recorded structurally (`CompletionSummary.substitutions`) and disclosed when the answer does not name both sources (S16-T1 `276f30`).

Probes after all fixes (PROBE-B): S16-T1 `f22c3b` PASS (substitution stated), S16-T2 `50278e` PASS (4 calls / 27.0k, layer removed, Tokyo framed, no provider call, verified), S08-T1 `44deb6` PASS, S08-T2 `28e8eb` PASS (full answer kept, no gate violation).

## Remaining gaps, most important first

1. Full-suite re-run of the post-suite fixes (only S08 and S16 probed).
2. S12-T4 / S09-T2 cost (~66k each); call 3 is a model text stop that needs one targeted correction.
3. S13 framing for countries with remote territories (Portugal + Azores).
4. S07 does not explain the impossible magnitude; S06 uses two Open-Meteo capabilities; S02 aside about time zones.
5. S16-T2 answer is the terse state summary ("Visible overlays: none") rather than naming Tokyo.
6. Provider 429 recovery still unexercised live.
