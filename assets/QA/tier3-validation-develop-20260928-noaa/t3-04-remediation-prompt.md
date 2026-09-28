# Prompt for reliable T3-04 remediation

Work in the AEGIS Geospatial View repository and resolve the current NOAA
`T3-04` validation blocker. The exact configured lane is
`opencode-go / deepseek-v4.1-flash`; do not substitute another provider or
model and do not count fallback output as success.

Investigate the live NOAA active-alert response around Houston. If an alert
has a null or otherwise unusable `geometry` but exposes official NWS
`affectedZones`, resolve those provider-owned forecast-zone resources on the
server, normalize their GeoJSON boundaries, and compose a renderable geometry
without trusting model-supplied URLs or geometry. Bound and cache the lookups,
preserve alert data when a zone lookup is temporarily unavailable, and report
an explicit partial/data-only result in that failure case. Do not turn a
non-renderable response into a renderer success and do not misclassify a real
empty active-alert result.

Update the renderer admission, bounds, and GeoJSON conversion paths as needed
so normalized polygon, multipolygon, and geometry-collection features are
handled consistently. Add focused tests for successful affected-zone
resolution, strict URL filtering and deduplication, temporary zone failure,
normalized geometry admission, and render-data conversion. Run the focused
suite plus the adjacent agent/map-plan regressions, Ruff, and strict Pyright.

Then validate the exact lane in the real browser with the request:

> Show me current NOAA weather alerts around Houston, Texas.

Require all of the following for `T3-04 PASS`: the configured model is visibly
verified, NOAA returns a current feature or an honestly classified valid-empty
result, the map plan is accepted, the MapLibre GeoJSON source/layer is visible,
NOAA and basemap attribution are visible, and the run records render
acknowledgement and completion. If a required external prerequisite is
temporarily unavailable, keep that specific gate `BLOCKED` and document the
evidence and limitation. Update the canonical validation ledger and store all
QA artifacts under `assets/QA/`; commit and push the final changes.
