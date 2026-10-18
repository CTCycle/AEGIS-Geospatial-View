# T3-07 browser evidence

Exact-lane `opencode-go / deepseek-v4.1-flash` browser run against the isolated
runtime (`http://127.0.0.1:5079`). The in-app browser loaded the local frontend;
the backend served the rebuilt client bundle.

## Standalone raster passes

Both scenarios in `reports/RASTER-LIVE-DIAGNOSTICS.json` classified
`raster_render_pass`:

- **FEMA NFHL flood zones (New Orleans)**: 20 same-origin AEGIS proxy tile
  responses returned `200 image/png`; 0 direct-upstream browser requests. The
  overlay source loaded, the layer was visible, the canvas carried the rendered
  raster, attribution "Federal Emergency Management Agency" was present, and the
  server accepted `map.render_ack` with `render_status: ready`. Run
  `run_1ab047a42f564d3189cfb9662d4bbbc0` / conversation
  `conv_70d29f0ed5ed4c83b851dba677392df8`.
- **ESA WorldCover (Rome)**: 14 same-origin AEGIS proxy tile responses returned
  `200 image/png`; 0 direct-upstream. Source/layer/pixels/attribution
  ("© ESA WorldCover / Terrascope") and accepted `map.render_ack`
  (`render_status: ready`) all recorded. Run
  `run_c4467ef838424928a52271fe0c3e114c` / conversation
  `conv_53b670968e1e49459b1ca412c70c1030`.

The FEMA upstream request through the FEMA ArcGIS Online relay returned a
256×256 fully non-transparent PNG (65,536 non-transparent / non-white pixels)
for the New Orleans layer-28 tile, both via the live proxy and via the relay
directly.

## FEMA composition / removal boundary

The FEMA standalone render and its overlay toggle are validated. Composing FEMA
with a partner layer at one viewport is limited by NFHL layer 28's scale
dependency (zoom ≥ 14): ESA WMS did not load at z14, USGS gauges fell outside
the z14 tile viewport (0 visible features), GIBS failed the z14 raster probe,
and Census TIGERweb timed out. See `report.md`.

Screenshots: `screenshots/RASTER-LIVE-DIAGNOSTICS/fema_new_orleans.png`,
`screenshots/RASTER-LIVE-DIAGNOSTICS/esa_worldcover_rome.png`,
`manual-fema-standalone.png`.