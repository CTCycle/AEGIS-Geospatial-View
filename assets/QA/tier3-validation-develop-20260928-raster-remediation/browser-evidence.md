# Browser observations — Tier 3 public raster follow-up

- Date: 2026-09-28
- Tested source: `develop@be61298ddf4ae1c0b6900810b046c10d97e4993a`
- Provider/model: `opencode-go / deepseek-v4.1-flash`
- Runtime: isolated `runtimes/cache/test-runtime/tier3-raster-remediation-20260928`
- Browser: Codex in-app Browser at `http://127.0.0.1:4512/`

## Provider readiness

The Settings view showed OpenCode Go selected with `deepseek-v4.1-flash`; the agent status became **Verified**. The native structured probe passed at `2026-09-28T14:52:31.576093Z`, with `parse_status=complete` and `protocol=openai-chat-completions`. No provider or model substitution was observed. See [provider-probe.json](provider-probe.json).

## Scenarios

| Scenario | Run ID | Browser and persisted result | Acceptance |
| --- | --- | --- | --- |
| FEMA NFHL standalone, New Orleans | `run_159619620ee74aa98ff11917d26d9836` | Provider retrieval returned `result_status=ok`, `map_eligibility=renderable`, FEMA attribution, and a raster-tile descriptor. Two MapLibre render attempts failed. Final bounds were `[-90.1399307, 29.8654809, -89.6251763, 30.1994687]`; run version 1, collection revision 1, map session `candidate-841eb8416468462b820a5d1a0b4b553e`. | `status=failed`, `failure_stage=maplibre`, `source_present=false`, `layer_present=false`, `zoom_range_valid=false`; all required source/layer/viewport checks false. Acknowledgement status is failed for the matching run/session/revision. No FEMA pixels or accepted `map.render_ack`. |
| USGS gauges after FEMA failure | `run_2a10da588f54475a95f78a336464f0a4` | USGS rendered alone in the same conversation. The visible map showed six gauge features, USGS attribution, and the OpenStreetMap basemap. Bounds were `[-90.14217156449374, 29.922158706079884, -89.69643954661628, 30.179948004173937]`; run version 1, revision 1, session `candidate-b6ef782157f74e9cb78619daa5082e1d`. | Ready acknowledgement; source, layer, zoom, style, visibility, and viewport checks passed for USGS. This was not FEMA+USGS composition because FEMA was absent. |
| Remove gauges while keeping FEMA | `run_74fcdd6260384a8eb02ac25c890e0b4c` | The browser showed the attributed OpenStreetMap basemap with no visible overlays. Revision 2, session `candidate-d4cdb1ff78f440cc9b60ecd37de5447b`; the final overlay list was empty. | Ready acknowledgement for the empty overlay state. FEMA retention was not met: FEMA had never loaded or entered the visible map state. `GEO-HYD-06` remains blocked on a verified FEMA render. |
| ESA WorldCover standalone, Rome | `run_b5095da78bf84dea8dbc68a766b34cfa` | Rome resolved to center `(12.4829, 41.8933)` and expected bounds `[12.2344416, 41.6556417, 12.8557603, 42.1410285]`. Provider retrieval returned a renderable WorldCover descriptor with `© ESA WorldCover / Terrascope` attribution. Both the OSM and Esri World Imagery candidate attempts failed. Final run version 1, revision 1, session `candidate-9867e088539b497bb05f8af29cba47b9`. | `status=failed`, `failure_stage=maplibre`, `source_present=false`, `layer_present=false`, `zoom_range_valid=false`; required source/layer/viewport checks false. The matching acknowledgement status is failed; no raster pixels or accepted `map.render_ack`. |

The FEMA descriptor resolved to the public ArcGIS export endpoint `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export` with bbox, spatial reference, size, format, transparency, and image query parameters. The ESA descriptor carried URL `services.terrascope.be/wmts/v2`, layer `WORLDCOVER_2021_MAP`, matrix set `EPSG:3857`, PNG format, and empty style metadata. Descriptor fields are summarized in [run-summary.json](run-summary.json); full URLs and credential-bearing values are intentionally not retained.

## Diagnosis boundary

The structured provider probe, descriptor regression tests, attribution, and candidate construction all passed. The browser reports a generic MapLibre source-load failure, and persisted acknowledgement details confirm both raster sources and layers are absent. USGS succeeds through the same application and MapLibre runtime, but that does not validate the separate raster URL paths.

A direct navigation to the official ESA GetCapabilities URL displayed `ERR_HTTP2_PROTOCOL_ERROR`. The Browser API exposes console logs but no network events or HTTP status codes; the local HTTP request attempt was also blocked by sandbox socket permissions. Therefore the evidence does **not** conclusively assign the raster load failure to a repository URL-construction defect or to the remote service/network. No speculative renderer or public-contract change was made. `ISSUE-002` remains open pending request-level telemetry or a successful live raster render.

The in-app Browser displayed screenshots inline, but its API did not expose a local screenshot file path. No screenshot binary is included or claimed. See [console-network-summary.json](console-network-summary.json) for the sanitized diagnostic inventory.
