# T3-14 browser-authoritative evidence

Exact lane `opencode-go / deepseek-v4.1-flash`; isolated disposable runtime on
port 5079; structured probe passed. Evidence captured by
`test_live_vector_point_matrix.py` (VECTOR-POINT-MATRIX-LIVE) with
`APP_TEST_SCENARIO_FILTER=t3_14_gbif_lugano,t3_14_gbif_valid_empty`.

## t3_14_gbif_lugano — `map_render_pass`

- Prompt: `Show species occurrences within 5 kilometers of Lugano,
  Switzerland.`
- Selected capabilities: `gbif_species_occurrences`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked.
- Attribution: `GBIF.org and contributing datasets`.
- Run trace: `render_observed` `ready`; `render_checks` all true.
- Network: 20 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

## t3_14_gbif_valid_empty — `map_render_pass`

- Prompt: `Show species occurrences within 10 kilometers of latitude 48.5,
  longitude -128.5.` (open Pacific off Vancouver Island).
- Selected capabilities: `gbif_species_occurrences`, `osm_default`.
- The location returned marine occurrence records this run, so the overlay
  rendered as a loaded clustered-point layer rather than an empty no-results
  state; the point-insight render boundary is proven and the honest
  no-observations sub-scenario is recorded as not separately empty this run.
- Attribution: `GBIF.org and contributing datasets`.
- Run trace: `render_observed` `ready`.
- Network: 35 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

Screenshots: `screenshots/VECTOR-POINT-MATRIX-LIVE/`. Per-scenario HTTP capture
and run traces: `http/VECTOR-POINT-MATRIX-LIVE/`. Aggregate:
`reports/VECTOR-POINT-MATRIX-LIVE.json`.