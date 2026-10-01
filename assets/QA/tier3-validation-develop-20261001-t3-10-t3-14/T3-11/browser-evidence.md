# T3-11 browser-authoritative evidence

Exact lane `opencode-go / deepseek-v4.1-flash`; isolated disposable runtime on
port 5079; structured probe passed. Evidence captured by
`test_live_vector_point_matrix.py` (VECTOR-POINT-MATRIX-LIVE) with
`APP_TEST_SCENARIO_FILTER=t3_11_coops_charleston,t3_11_radar_houston`.

## t3_11_coops_charleston — `map_render_pass`

- Prompt: `Show coastal water level stations around Charleston, South
  Carolina.`
- Selected capabilities: `noaa_coops_water_levels`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked.
- Attribution: `NOAA CO-OPS`.
- Run trace: `render_observed` `ready`; `render_checks` all true.
- Network: 31 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

## t3_11_radar_houston — `map_render_pass`

- Prompt: `Show current radar over Houston, Texas.`
- Selected capabilities: `noaa_radar`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked.
- Attribution: `NOAA/NCEP nowCOAST`.
- Run trace: `render_observed` `ready`; `render_checks` all true.
- Network: **48 same-origin proxy requests, `proxy_capabilities_seen =
  [noaa_radar, osm_default]`, 0 direct-upstream browser requests** — the radar
  raster renders through the same-origin AEGIS tile proxy.
- Terminal: `completed`.

Screenshots: `screenshots/VECTOR-POINT-MATRIX-LIVE/`. Per-scenario HTTP capture
and run traces: `http/VECTOR-POINT-MATRIX-LIVE/`. Aggregate:
`reports/VECTOR-POINT-MATRIX-LIVE.json`.