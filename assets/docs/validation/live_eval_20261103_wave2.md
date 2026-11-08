# Wave 2 Live Evaluation Summary

Last updated: 2026-11-03

Live validation of the Wave 2 remediation (`develop@740792f4`, on top of `e4e593a6`: H-04 independent place resolution, M-02 per-target route scopes, M-07 live eval runner; and the world-extent ack, forecast observation time and M-01 bounded route revision) on OpenCode Go `deepseek-v4.1-flash` and `beam-free`. Built SPA, backend on port 5002, built-in browser with the pane visible. Part A is the graded runner (`--no-render`, matrix plus holdout); Part B re-runs the Wave 1 FAIL, PARTIAL and BLOCKED turns and the Wave 2 scenarios in the browser. Full evidence (traces, screenshots, analysis) is untracked under `assets/QA/agent-loop/w2-validation-20261103/`.

## Counts

Browser turns. The turn sets are not like-for-like with Wave 1: this run re-runs only the Wave 1 non-PASS turns (DeepSeek 10, Beam 15 of 16; Beam S08-t2 was not run because S08-t1 failed) plus the Wave 2 scenarios.

| Lane | Turns | PASS | PARTIAL | FAIL | BLOCKED | False successes |
|---|---|---|---|---|---|---|
| DeepSeek v4.1 Flash | 18 | 7 | 6 | 3 | 2 | 0 |
| Beam Free | 24 | 8 | 5 | 11 | 0 | 0 |
| Wave 1, DeepSeek | 28 | 18 | 4 | 4 | 2 | 0 |
| Wave 1, Beam | 20 | 4 | 5 | 10 | 1 | 2 |

False-success gate (target 0): **MET** under the strict definition (answer or stored completion claims success while the map or evidence disagrees). Beam's magnitude-filter follow-up now fails honestly and its recap says the filter was not applied. Six borderline map or window claims are listed in the QA report and not counted (framing, M-03, plus one undisclosed forecast-window overclaim on Beam).

Movement on the re-run Wave 1 turns: DeepSeek R4b FAIL to PASS, R2 tomorrow FAIL to PARTIAL, J2 PARTIAL to FAIL; Beam E-t4 FAIL (false success) to PASS, R4b FAIL to PASS, R2 tomorrow FAIL to PARTIAL, B4 PARTIAL to FAIL, A3 BLOCKED to FAIL; everything else unchanged.

## Wave 2 scenario results

| Scenario | DeepSeek | Beam Free |
|---|---|---|
| H-04 Paris, then the Colosseum | PASS: Rome | PASS |
| H-04 Rome, then the city centre | PASS: no clarification | FAIL: resolver and map-plan tool failures, honest stop |
| H-04 Berlin, then the Brandenburg Gate | PARTIAL: asks Berlin or Kaliningrad | PASS |
| M-02 rainfall today in Rome, tomorrow in Milan | PARTIAL: `target_requirements` and tool windows correct per city; provider returns one rolling 24 h window for both, disclosed | PARTIAL: same evidence window, Milan "tomorrow" total stated without disclosing it |
| M-01 worldwide quakes, then magnitude above 5 | PASS: re-queried, 206 events, map filtered | FAIL, honest: route revision, then provider error; map unfiltered, no filter claim |
| World-extent render | PASS: ack `ready` | PASS: ack `ready` (one first attempt sat in "rendering" for 35 s or more and was superseded; not reproduced) |

Incorrect geographic reuse: **0**.

## Runner grades (`--no-render`, 28 matrix plus 10 holdout scenarios)

| | DeepSeek | Beam Free |
|---|---|---|
| Passed / failed | 25 / 13 | 22 / 16 |
| False-success flags | 0 | 0 |
| termination (pass / fail) | 34 / 4 | 28 / 10 |
| route (pass / fail / n/a) | 28 / 3 / 7 | 27 / 4 / 7 |
| tools (pass / fail) | 34 / 4 | 34 / 4 |
| provenance (pass / fail / n/a) | 31 / 1 / 6 | 32 / 0 / 6 |
| render (fail / unverified / n/a) | 6 / 16 / 16 | 3 / 18 / 17 |
| answer (pass / n/a) | 22 / 16 | 14 / 24 |

Neither model has a baseline entry, so the gate passed on the false-success check alone. The runner did not misbehave. Its default `--base-url` is not port 5002, so the first invocation exited 2 with a bare connection error; passing `--base-url http://127.0.0.1:5002` fixed it and no file was changed.

## Cross-target violations

- Beam Switzerland precipitation (C4): 3 of the top-5 points are in Liechtenstein and Austria, a marker sits near Besançon, and all values are 0 mm (labels disclose the country). The same pattern as the Wave 1 Italy case.
- Per-target evidence windows: the Open-Meteo forecast tool returns a rolling 24 h window from the current time, so Milan "tomorrow" is never fully covered on either model. No place or evidence was reused across targets.

## Open issues

- **Every route revision ends in a failed run (new, M-01).** 13 of 13 runs that recorded `route_revisions` failed (12 `provider_api`, 1 with no category): Beam on six browser turns and seven runner scenarios, DeepSeek on one runner scenario. The stored revision record has no `outcome`, so the revision routing call raised and the exception ended the run. Suspect: `_revise_route` and the `revision=` path of `_route` in `app/server/services/agent/agent_loop.py`; the provider error text was not captured. Not verified.
- **Framing (M-03).** Multi-point maps still place markers at viewport edges, under the location pill or out of view (Lugano, Rome in the Rome/Milan comparison, Zurich and Geneva, Beam's Greek rainfall maximum), and answers still say "the map shows both".
- **Forecast window (M-05).** The forecast capability cannot cover a calendar day other than the next 24 h.
- **Routing and discovery.** "No capability" for forecast maximum-temperature wording and for "NASA GIBS yesterday"; a MODIS layer name treated as a place (Beam); a question about existing evidence sent to discovery (Beam E-t3).
- **Model behaviour (H-03).** Repeated invalid tool calls on the 400-day Tokyo M>15 request on both models; DeepSeek never explains that magnitude 15 is impossible.
- **Provider (M-05).** ourairports and Overpass failures on the airport and schools requests (DeepSeek).

## Remaining FAIL / PARTIAL classification

| Class | Turns |
|---|---|
| Routing: route revision failure (M-01) | Beam M01-t2, INV3, E-t2, B4, S08-t1, A3; runner Beam physical, transit, crime, neighbourhood POI, bbox weather, historical weather and seismic discovery; DeepSeek boundary |
| Model behaviour (H-03) | DeepSeek J2; Beam J2, city-centre |
| Render / timeout / framing (M-03) | DeepSeek and Beam B2; DeepSeek M02; DeepSeek and Beam R2 tomorrow; Beam C1 |
| Provider / external or capability gap (M-05) | DeepSeek A3, A5, R2 past, INV3 (cloud cover); DeepSeek and Beam M02 window |
| Routing / discovery | DeepSeek R2 future, R3 attempt 1; Beam R3 Africa, R3 world LST, E-t3 |
| Other | DeepSeek Brandenburg Gate clarification; Beam C4 scope (cross-target points) |

## Setup notes

`FASTAPI_PORT=5002` must be in the process environment for the WebSocket origin check. The browser pane is 800 px wide by default; the app requires 1024 px, so the viewport was emulated at 1280x800. Each turn started a new conversation; reloading the page restores the previous conversation, which silently carries its context into the next prompt.
