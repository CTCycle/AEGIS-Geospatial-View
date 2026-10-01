# T3-10 browser-authoritative evidence

Exact lane `opencode-go / deepseek-v4.1-flash`; isolated disposable runtime on
port 5079; structured probe passed. Evidence captured by
`test_live_vector_point_matrix.py` (VECTOR-POINT-MATRIX-LIVE) with
`APP_TEST_SCENARIO_FILTER=t3_10_earthquakes_tokyo,t3_10_earthquakes_valid_empty`.

## t3_10_earthquakes_tokyo — `map_render_pass`

- Prompt: `Show recent earthquakes around Tokyo, Japan.`
- Route: execute, `retrieve_recent_earthquakes`, target `Tokyo, Japan`.
- Selected capabilities: `usgs_earthquakes`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked.
- MapLibre canvas present (1).
- Attribution: `U.S. Geological Survey`.
- Run trace: `render_observed` `ready`; `render_checks`
  `{required_sources_loaded: true, required_layers_present: true,
  viewport_valid: true}`.
- Network: 32 same-origin proxy requests (`osm_default` tiles), **0
  direct-upstream browser requests**.
- Terminal: `completed`.

## t3_10_earthquakes_valid_empty — `map_render_pass`

- Prompt: `Show recent earthquakes within 100 kilometers of latitude 0,
  longitude -140.`
- Location resolved as point coordinates (0, -140) with high confidence.
- Selected capabilities: `usgs_earthquakes`, `osm_default`.
- Provider outcome: `valid_empty` (honest "no matching earthquakes"; the
  capability was the only eligible earthquake/seismic candidate).
- Map rendered (canvas present) and the run completed normally with an
  accepted `render_observed` `ready` acknowledgement; the no-results boundary
  did not degrade into a failed tool loop (the historical T3-04 failure shape).
- Network: 16 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

Screenshots: `screenshots/VECTOR-POINT-MATRIX-LIVE/`. Per-scenario HTTP capture
and run traces: `http/VECTOR-POINT-MATRIX-LIVE/`. Aggregate:
`reports/VECTOR-POINT-MATRIX-LIVE.json`.