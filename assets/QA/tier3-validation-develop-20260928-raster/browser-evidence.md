# Browser evidence boundary

The Codex in-app browser was used before the controlled headless browser
module. The visible saved FEMA New Orleans conversation showed:

- FEMA data retrieval metadata present.
- Assistant state: unable to produce a verified map.
- Failure: `render_failed` at MapLibre, with overlay source absent and layer
  not present.
- Map canvas remained at the empty prompt state.
- Agent model state: `Not verified` after the current exact-lane probe failure.

The saved conversation is not a fresh live-provider run and is therefore not
promoted to a current raster render result. The controlled Angular geospatial
module then ran in ChromeHeadlessNoGpu and passed 6/6, including mocked WMTS
descriptor rendering. That validates the client contract only; it does not
replace live source/layer presence, visible pixels, attribution, and
`map.render_ack` evidence.

No binary screenshot is claimed because the in-app browser did not export a
local image in this run.
