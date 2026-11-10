# Wave 3 Live Evaluation Summary

Last updated: 2026-11-03

Live validation of the Wave 3 remediation (`develop@d4f4c1e2`: H-03 rejection-feedback contract, budget forgiveness and the `unsupported_request` / `model_incapable` terminal reasons; M-05 provider temporal windows, failure classification, bounded retry and mirror fallback; M-03 framing padding, `targets_in_view` and classified render deadlines; discovery recall for capability variables, dated GIBS layers, catalog names and cloud cover) on OpenCode Go `deepseek-v4.1-flash` and `beam-free`. Built SPA, backend on port 5002, built-in browser with the pane visible (`visibilityState` read as `visible` before the first turn, after each lane and before closing). Part A is the graded runner (`--no-render`, matrix plus holdout); Part B re-runs every Wave 2 FAIL, PARTIAL and BLOCKED browser turn plus the Wave 3 framing, forecast-window, H-03 and discovery checks. Full evidence (traces, screenshots, analysis, proposed baseline) is untracked under `assets/QA/agent-loop/w3-validation-20261103/`.

## Counts

Browser turns. The turn sets are not like-for-like with Wave 2: Wave 3 re-runs the Wave 2 non-PASS turns (with their prerequisite turns) and adds the framing, H-03 and discovery checks; Beam S08-t2 was not run (prompt not recorded).

| Lane | Turns | PASS | PARTIAL | FAIL | BLOCKED | False successes |
|---|---|---|---|---|---|---|
| DeepSeek v4.1 Flash | 21 | 11 | 3 | 5 | 2 | 1 |
| Beam Free | 25 | 9 | 6 | 9 | 1 | 1 |
| Wave 2, DeepSeek | 18 | 7 | 6 | 3 | 2 | 0 |
| Wave 2, Beam | 24 | 8 | 5 | 11 | 0 | 0 |

False-success gate (target 0): **MISSED**, 2 under the strict definition (answer or stored completion claims success while the map or evidence disagrees).
- DeepSeek "Show the Brandenburg Gate" after "Show Berlin": the landmark resolver failed, the model fell back to the Berlin viewport and the run completed `goal_satisfied`; the answer ("The map now shows Berlin") is true but never says the Gate was not found. Stored-completion-only.
- Beam recap "Summarize what we found so far": states "Filtered to magnitude > 5: 2 features returned" although the preceding fetch carried no magnitude filter and the two features include an M4.8 event; the recap hedges that the records were not fully inspected.

Movement on the re-run Wave 2 turns (DeepSeek, Beam): B2 PARTIAL to PASS, PARTIAL to PASS; R2 tomorrow PARTIAL to PASS, PARTIAL to PASS; J2 FAIL to PASS, FAIL to PASS; R2 future FAIL to PASS (DeepSeek); R4b/M01 filter PASS to PASS (DeepSeek), FAIL to FAIL (Beam, honest, new cause); C1 PARTIAL to PASS (Beam); S08-t1 FAIL to PASS (Beam); H04b city centre FAIL to PARTIAL (Beam); R3 Africa FAIL to PARTIAL (Beam); E-t4 recap PASS to FAIL (Beam, false success); R2 past PARTIAL to FAIL (DeepSeek); C4 PARTIAL to FAIL (Beam); H04c Brandenburg Gate PARTIAL to FAIL (DeepSeek); A3 BLOCKED to BLOCKED (DeepSeek), FAIL to BLOCKED (Beam); A5 BLOCKED to BLOCKED; INV3 PARTIAL to PARTIAL (DeepSeek), FAIL to FAIL (Beam); M02 PARTIAL to PARTIAL on both.

## Wave 3 checks

| Check | DeepSeek | Beam Free |
|---|---|---|
| Framing: "Show Paris and Berlin" | FAIL: only Paris framed (two `set_viewport fit_location` actions, Berlin off screen); no `targets_in_view` key (no marker overlays) | FAIL, identical |
| Framing: "Compare weather in Lugano and Milan" | PASS: both markers visible, `targets_in_view: true` | PASS: answer only (`inspect` route, no map) |
| Framing: Rome today vs Milan tomorrow | PARTIAL: both markers visible, `targets_in_view: true`; the answer is a generic map sentence with no comparison | PARTIAL: no map; Rome "today" evidence covers one hour (disclosed) |
| Forecast window: Milan covers tomorrow's calendar day | PASS: Milan 2026-11-04 full day, `temporal_scope_satisfied: true` | PASS for Milan (00:00 to 23:00); Rome "today" is a rolling window |
| H-03: Tokyo M>15, 400 days | PASS: `unsupported_request` after three failed executes (366-day provider limit), no loop | PASS, same |
| H-03: worldwide quakes, then magnitude above 5 | PASS: EMSC mirror fallback disclosed, then re-query, 223 events, map filtered | FAIL, honest: invented evidence ref, "stopped after repeated tool failures", map unfiltered, no claim |
| Discovery: maximum temperature tomorrow in Madrid | PASS (14.3 C) | PASS |
| Discovery: NASA GIBS imagery over Italy yesterday | FAIL: dated layer found, raster evidence lacks temporal coverage, map rejected | FAIL, same cause |
| Discovery: cloud cover over Zurich tomorrow | PARTIAL: data fetched, generic fallback answer | PARTIAL, same |
| Discovery: Japan this month, then "Which one is the strongest?" | PASS: answered from existing evidence only | PARTIAL: invented ref, fresh fetch, run ends failed with a correct answer |

Incorrect geographic reuse: **0**.

## Runner grades (`--no-render`, 28 matrix plus 10 holdout scenarios)

| | DeepSeek | Beam Free |
|---|---|---|
| Passed / failed (Wave 2) | 27 / 11 (25 / 13) | 23 / 15 (22 / 16) |
| False-success flags | 0 | 0 |
| termination (pass / fail) | 35 / 3 | 31 / 7 |
| route (pass / fail / n/a) | 29 / 2 / 7 | 25 / 6 / 7 |
| tools (pass / fail) | 34 / 4 | 28 / 10 |
| provenance (pass / fail / n/a) | 31 / 1 / 6 | 30 / 2 / 6 |
| render (fail / unverified / n/a) | 6 / 17 / 15 | 2 / 21 / 15 |
| answer (pass / n/a) | 21 / 17 | 14 / 24 |

Neither model has a baseline entry, so the gate passed on the false-success check alone. A per-model baseline was proposed but not applied: DeepSeek is a clean improvement, Beam carries the three regressions below).

Regressions (pass to fail):
- DeepSeek: none. Fail to pass: `holdout-poi-parent-chain-3`, `holdout-followup-entity-9`.
- Beam, three: `physical-elevation-coordinate` and `compound-air-quality-roads` (5 and 6 model-induced invalid calls, limit 3: the model calls the unexposed `search_geospatial_catalog` and fails several `describe_geospatial_capability` validations; the runs still complete), and `follow-up-preserve-location-change-metric` (turn 2 calls another unexposed tool, repeats `resolve_geospatial_location`, ends `agent_operation_failed` with the generic fallback). Cause: Beam model behaviour. Fail to pass: `unsupported-crime-statistics`, `scale-bounding-box-weather`, `follow-up-context-answer`, `holdout-poi-parent-chain-3`.

## Route revision (M-01 follow-up)

Revisions recorded in the Wave 3 runs: 9, all with `outcome: revised` (Wave 2: 13 of 13 had no outcome and failed). Of the 9, 3 completed, 5 failed for other reasons (render checks, call budget, provider) and 1 was cancelled by the runner. The Wave 2 revision-crash defect is fixed.

## Cross-target violations

- Beam Switzerland precipitation (C4): 4 of the top-5 points are in Italy (Alagna Valsesia, Rossa, Trontano, Alto Sermenza); the answer is a bare list that does not say so. Worse than Wave 2 (3 of 5, labelled).
- No place or evidence was reused across targets.

## Answer-quality issues

Generic "Results gathered so far" fallback: DeepSeek R2-past and cloud cover; Beam INV3, R3 world LST, Japan this month, magnitude filter, GIBS Italy, cloud cover and B4 (after a real list); runner `follow-up-preserve-location-change-metric` (Beam). Other non-answers: DeepSeek Rome/Milan rainfall (a map sentence with no comparison) and GIBS Italy ("Render recovery requires a materially different map action."); Beam "Show the city centre" ("Map state update verified ... Visible overlays: none"); Beam C4 (no scope disclosure). None is empty.

## Open issues

- **Multi-location show frames one target (render/framing).** "Show Paris and Berlin" ends on Paris on both models; with no marker overlay the `targets_in_view` ack key is absent, so the check cannot fail. Suspect `map_session_builder` handling of repeated `set_viewport` and `targetsInViewCheck` in `map-preview.component.ts`.
- **Dated GIBS rasters fail map validation (provider/map validation).** The raster evidence coverage has no `temporal_scope_satisfied`, so `apply_map_plan` rejects with "requested time window was not verified" although the capability ran with the right date. Suspect the GIBS raster result builder and the validator's time-window check.
- **Beam calls unexposed tools and invents evidence refs (model behaviour).** `search_geospatial_catalog` appears in 12 of 25 Beam browser turns (0 of 21 on DeepSeek) and costs budget; invented refs break the magnitude-filter and strongest-event follow-ups.
- **Generic fallback answers and false claims at completion (finalization).** Stored completion `goal_satisfied` with an unresolved landmark or an unapplied filter. Suspect `final_answer_check.py` and the fallback summariser.
- **Render (Beam).** B4's earthquake map ack failed (`render_timeout`, sources never loaded) with the pane visible, and the world-extent LST overlay fails render checks; neither reproduced elsewhere.
- **Routing and discovery.** Cloud cover is not requested in the stargazing grid; R2 past picked a MODIS land-surface-temperature raster for air temperature; "this month" starts 30 days back on Beam.
- **Provider (M-05).** ourairports (airports) and Overpass (schools) remain unavailable; USGS fell back to EMSC once.

## Remaining FAIL / PARTIAL classification

| Class | Turns |
|---|---|
| Model behaviour | DeepSeek Brandenburg Gate; Beam magnitude filter, INV3, strongest quake, keep above magnitude 5; runner Beam physical-elevation, compound-air-quality-roads, follow-up-preserve |
| Render / framing | DeepSeek and Beam Paris and Berlin; Beam B4 and world LST |
| Provider / external | DeepSeek A3, A5; Beam A3; Beam Rome "today" window |
| Routing / discovery | DeepSeek R2 past, INV3, R3 Africa, GIBS Italy; Beam C4, R3 Africa, Japan this month, GIBS Italy |
| Finalization / answer quality | DeepSeek Rome/Milan, cloud cover; Beam city centre, cloud cover, recap (false success) |

## Setup notes

`FASTAPI_PORT=5002` in the process environment and `--base-url http://127.0.0.1:5002` for the runner. The browser viewport was emulated at 1280x800; each turn sequence started a new conversation with the `+` button (a reload restores the previous conversation). The model was switched with the model fields of `PATCH /api/chat/settings` and restored to `opencode-go / deepseek-v4.1-flash`; no credential was entered or changed.
