# Wave 1 Live Evaluation Summary

Last updated: 2026-11-03

Live UI validation of the Wave 1 remediation (`develop@6880a510`: H-01 per-target completion, H-02 raster render ack, H-05 final-answer reconciliation, M-04 off-loop evidence writes) on OpenCode Go `deepseek-v4.1-flash` and `beam-free`. Built SPA, backend on port 5002, built-in browser with the pane visible. Full evidence (traces, screenshots, analysis) is untracked under `assets/QA/w1-validation-20261103/`.

## Counts

Turns are not like-for-like with the 2026-11-02 baseline: the baseline counted re-runs and had no regression turns; this run has none of the re-runs and adds six regression turns per lane.

| Lane | Turns | PASS | PARTIAL | FAIL | BLOCKED | False successes |
|---|---|---|---|---|---|---|
| DeepSeek v4.1 Flash | 28 | 18 | 4 | 4 | 2 | 0 |
| Beam Free | 20 | 4 | 5 | 10 | 1 | 2 |
| Baseline 2026-11-02, DeepSeek | 27 | 20 | 3 | 3 | 1 | 1 (H1 first attempt) |
| Baseline 2026-11-02, Beam (round 2) | 19 | 7 | 7 | 5 | 0 | not counted |

One DeepSeek run made with the page hidden is excluded (`INVALID`). Gate target of zero false successes: **MISSED** (2, both Beam, one root cause).

## Wave 1 regression results

| Scenario | DeepSeek | Beam Free |
|---|---|---|
| H1 replay (Paris and Berlin) | PASS: both markers rendered, no unrendered claim; markers sit at viewport corners | PASS (same framing note) |
| Two cities, past date | PARTIAL: honest "no capability satisfies the time window" | not run |
| Two cities, forecast | FAIL (two phrasings): discovery found nothing, or temporal scope never satisfied and the budget ran out; both honest | FAIL: repeated tool failures, honest |
| Large GIBS raster | PASS: ack `ready` only after the source loaded, imagery visible, MODIS to VIIRS substitution disclosed | PASS for VIIRS Europe; two other phrasings FAIL (no capability or place clarification) |
| Worldwide earthquakes, 30 days | FAIL: map never rendered, run stored `render_timeout`; UI stayed responsive | FAIL (same) |

The failing-tile branch of the raster ack was not exercised live.

## Open issues

- **Worldwide earthquakes never render (both models, M-03).** The server rejects `map.render_ack` with a validation error (`realtime_command_payload_rejected`) and the run times out after 90 s; the final text stays "Data prepared; the map is loading." Suspect: the viewport-bounds range check in `app/server/domain/realtime.py` for a world-extent view.
- **Beam false success on a filter follow-up (H-01/H-05, M-01/M-02).** "Only keep those above magnitude 5" was routed as a map restyle, a transform failed, the run ended `goal_satisfied`, and the later summary claimed the filter was applied while the map still showed all events.
- **Cross-target scope.** Beam's Switzerland forecast ranked three points in Italy as top Swiss results (labels disclose the country). DeepSeek's Italy earthquake map used the country bounding box and disclosed that border events fall outside Italy.
- **Beam model behaviour (H-03).** Four of ten Beam FAIL turns end on repeated invalid tool calls or the model-call limit.
- **Routing and discovery (M-01/M-02).** Forecast maximum-temperature wording, "NASA GIBS" wording, follow-up questions about existing evidence and the cloud-cover capability gap return "no capability".
- **Two-city forecast on DeepSeek.** `temporal_scope_applied` was never satisfied after both cities were fetched (suspect the per-target temporal check in `completion.py`).
- **Framing (M-03).** Multi-point maps place markers at viewport edges or under map controls (Paris/Berlin, Lugano/Milan, Europe rain).
- **Provider (M-05).** ourairports and Overpass failures on the airport and schools requests; no cause verified beyond the honest provider-unavailable message.

## Setup notes

The documented start command must run from `app/`, not `app/server/`. `settings/.env` sets `FASTAPI_PORT=7059`, so for port 5002 the WebSocket origin check rejects the browser (HTTP 403) unless `FASTAPI_PORT=5002` is in the process environment.
