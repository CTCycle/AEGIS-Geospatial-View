# Tier 3 vector composition browser evidence

Run date: 2026-09-26.

The run used the configured `opencode-go / deepseek-v4.1-flash` lane in the
isolated runtime at `runtimes/cache/test-runtime/validation-20260924-exact-lane`.
No provider or model fallback was used. The Settings native tool probe was
`Verified` / `Native tool probe passed` before the live requests.

## Browser observations

| Slice | Request/action | Browser-visible result | Status |
| --- | --- | --- | --- |
| `T3-05` | `Show rivers and water features around Seattle, Washington.` | The Seattle map rendered with the Census TIGERweb Hydrography layer. The transcript reported 13 retrieved features and 15 features rendered in view; the layer panel showed `1 of 1 visible`, and the map showed Census attribution, OSM tiles, and MapLibre attribution. | **PASS** |
| `T3-06` composition | `Add active USGS water gauges around Seattle, Washington.` | The existing Census map remained while the update rendered. The final browser state showed Census hydrography plus USGS Water Gauges, `2 of 2 visible`, 13 + 2 features rendered, a combined evidence extent, both provider attributions, and a passed render check. | **PASS** |
| `T3-06` retention/removal | `Remove the USGS water gauges but keep the Census hydrography layer.` | The browser reported `Map state update verified`. USGS was removed; Census remained rendered and attributed with `1 of 1 visible`. | **PASS** |

The browser-control surface exposes screenshots inline but does not provide a
filesystem export path. The visual claims above are therefore based on the
inline rendered map captures and the corresponding accessibility state, with
no invented screenshot filenames.

## Carry-forward boundary

The same exact-lane Tier 3 run rechecked the public FEMA route: retrieval
returned FEMA NFHL data, but the FEMA raster source could not load in MapLibre,
so no FEMA layer was rendered or acknowledged. That remains the existing
`ISSUE-002` raster boundary; this vector result does not establish FEMA
composition or retention.
