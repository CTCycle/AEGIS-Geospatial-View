# T3-07 / T3-09 browser evidence — 2026-09-30

The official Windows launcher served the browser on `127.0.0.1:4512` with the
backend on `127.0.0.1:7059`. Settings showed the required exact lane
`opencode-go / deepseek-v4.1-flash`; the selected-model verification reported
`Verified` and `Native tool probe passed`.

The exact request was:

> Show the latest RainViewer precipitation radar over Naples, Italy

The completed run resolved Naples, executed `rainviewer_precipitation_radar`
as a `raster` result, prepared a raster-tile map candidate, and received
`render_observed=ready`. The visible UI reported:

- RainViewer Recent Precipitation Radar — latest observed frame;
- retrieved successfully and not stale;
- visible colored overlay over the Naples map;
- `© RainViewer` attribution;
- render check passed;
- latest-observed-only, no future nowcast or satellite IR, max zoom 7, and
  Universal Blue color scheme 2.

The MapLibre identity derived from the committed overlay instance was:

- source: `overlay-source-evidence:evidence_39ae9bb46b004538a95ae5f9a28bda5b:rainviewer_precipitation_radar`
- layer: `overlay-layer-evidence:evidence_39ae9bb46b004538a95ae5f9a28bda5b:rainviewer_precipitation_radar`

The first post-change live attempt exposed a contract drift: the provider
response reached the agent as `result_type=unknown`, so map application was
rejected as non-renderable. The narrow provider fix now sets `result_type=raster`
for both successful and empty RainViewer responses; the corrected run and unit
regression are recorded in `run-trace.json`.

The screenshot was captured in the Codex in-app Browser while the map and final
render status were visible. The browser-control surface exposes the capture
inline but did not provide a filesystem export path, so no binary screenshot or
provider body is retained in this QA directory. The browser tab was left as the
user-facing visual proof during validation.

Isolation boundary: a fresh QA data root initialized correctly but had no saved
OpenCode Go credential/model assignment. The successful exact-lane browser run
therefore used the launcher-configured canonical `data` root; no canonical
conversation or database cleanup was performed. This prevents a clean isolated
T3-09 PASS claim and is why the slice status remains `PARTIAL` despite the
functional browser proof.
