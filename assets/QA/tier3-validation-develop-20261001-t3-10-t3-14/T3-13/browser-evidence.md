# T3-13 browser-authoritative evidence

Exact lane `opencode-go / deepseek-v4.1-flash`; isolated disposable runtime on
port 5079; structured probe passed. Evidence captured by
`test_live_vector_point_matrix.py` (VECTOR-POINT-MATRIX-LIVE) with
`APP_TEST_SCENARIO_FILTER=t3_13_atmospheric_rome,t3_13_text_vs_map_boundary`.

## t3_13_atmospheric_rome — `map_render_pass`

- Prompt: `Show wind, humidity and pressure around Rome, Italy.`
- Selected capabilities: `openmeteo_pressure_humidity_wind`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked.
- Attribution: `© Open-Meteo`.
- Run trace: `render_observed` `ready`; `render_checks` all true.
- Network: 27 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

## t3_13_text_vs_map_boundary — `text_pass`

- Prompt: `What is the current wind speed in Milan, Italy?`
- Selected capabilities: `openmeteo_pressure_humidity_wind`,
  `get_weather_forecast` (numeric insight, no map).
- No map rendered (`maplibre_canvas_count=0`), no proxy requests, no
  `unexpected_map_rendered` classification.
- Terminal: `completed` — the pure numeric-insight request stayed on the
  text/direct-tool boundary.

Screenshots: `screenshots/VECTOR-POINT-MATRIX-LIVE/`. Per-scenario HTTP capture
and run traces: `http/VECTOR-POINT-MATRIX-LIVE/`. Aggregate:
`reports/VECTOR-POINT-MATRIX-LIVE.json`.