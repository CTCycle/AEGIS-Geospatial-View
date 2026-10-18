# T3-12 browser-authoritative evidence

Exact lane `opencode-go / deepseek-v4.1-flash`; isolated disposable runtime on
port 5079; structured probe passed. Evidence captured by
`test_live_vector_point_matrix.py` (VECTOR-POINT-MATRIX-LIVE) with
`APP_TEST_SCENARIO_FILTER=t3_12_buildings_rome,t3_12_poi_bologna,t3_12_poi_valid_empty`.

## t3_12_buildings_rome — `map_render_pass`

- Prompt: `Show residential buildings around the Colosseum, Rome, Italy.`
- Selected capabilities: `overpass_residential_buildings`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked; 510
  building footprints rendered (`rendered_feature_count=510`).
- Attribution: `© OpenStreetMap contributors (ODbL)`.
- Run trace: `render_observed` `ready`; `render_checks` all true.
- Network: 35 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

## t3_12_poi_bologna — `map_render_pass`

- Prompt: `Show nearby pharmacies around Bologna, Italy.`
- Selected capabilities: `overpass_poi_amenities`, `osm_default`.
- Overlay control row: `data-render-status=loaded`, visibility checked.
- Attribution: `© OpenStreetMap contributors (ODbL)`.
- Run trace: `render_observed` `ready`.
- Network: 36 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

## t3_12_poi_valid_empty — `map_render_pass`

- Prompt: `Show nearby pharmacies within 5 kilometers of latitude 25,
  longitude 13.` (central Sahara, Chad/Niger border).
- Selected capabilities: `overpass_poi_amenities`, `osm_default`.
- Provider outcome: `valid_empty` (honest no-results; the area has no mapped
  pharmacy infrastructure). The map rendered and the run completed normally
  with an accepted `render_observed` `ready` acknowledgement; the no-results
  boundary did not degrade into a failed tool loop.
- Network: 16 same-origin proxy requests, **0 direct-upstream browser
  requests**.
- Terminal: `completed`.

Screenshots: `screenshots/VECTOR-POINT-MATRIX-LIVE/`. Per-scenario HTTP capture
and run traces: `http/VECTOR-POINT-MATRIX-LIVE/`. Aggregate:
`reports/VECTOR-POINT-MATRIX-LIVE.json`.