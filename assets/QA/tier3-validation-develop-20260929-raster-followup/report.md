# AEGIS T3-07 / T3-08 raster follow-up — 2026-09-29

## Result

This follow-up started from `develop` at
`3ed9d99e032b6bb9eb5784c9fe47a24798dd58e0` and used the exact
`opencode-go / deepseek-v4.1-flash` lane. The structured provider probe passed
with `parse_status=complete`. Execution defaults were unchanged.

- **T3-07: `PARTIAL`.** FEMA and ESA still exercised the AEGIS same-origin tile
  proxy, with zero direct provider browser requests, but the public upstream
  connection failed before an image response. The AEGIS endpoint correctly
  returned normalized `502 application/json` responses. No FEMA or ESA
  MapLibre source/layer/pixel evidence or accepted raster `map.render_ack` was
  obtained, so the dependent FEMA composition/removal flow was not run.
- **T3-08: `PARTIAL`.** The staged non-temporal SRTM canary and temporal NDVI
  canary passed end to end. The remaining matrix evidence gives 11 rendered
  GIBS cases out of 12. The exact advertised MODIS fire case reached provider
  execution, but the live NASA GIBS catalog did not advertise the requested
  `MODIS_Combined_Thermal_Anomalies_Fire` layer and execution returned provider
  unavailable. No substitute dataset was used.

The campaign roll-up is now **30 `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 36
`UNRUN`**. T3-08 is no longer `UNRUN`: its product boundary was exercised and
classified from actual proxy, MapLibre, attribution, temporal, and
acknowledgement evidence.

## Repository defects found and repaired

The following defects were demonstrated by deterministic regressions or live
trace evidence and were fixed narrowly:

1. Raster upstream failures were collapsed into a generic provider error. The
   raster HTTP path now retains safe internal category/status/content-type/
   length/phase/host metadata and emits one sanitized terminal diagnostic while
   keeping the public error normalized.
2. The provider-layer discovery tool was registered as internal while its
   provider-discovery route required model-visible execution. Its exposure
   contract now matches that route, with positive and unrelated-route negative
   tests.
3. A model-selected `discover_capabilities` name and the `nasa_gibs` provider
   name were not both accepted by the canonical execution/registry paths. The
   narrow aliases now resolve without weakening general validation.
4. Point-resolved cities were filtered out of provider manifests that support a
   resolved bounding box. Provider discovery now lowers a point location to its
   available `bbox` scope for execution filtering.
5. GIBS WMTS requests hard-coded `max_zoom=9`, producing invalid Level6/7/8
   requests. The provider now derives the matrix-set ceiling from `LevelN`.
6. GIBS discovery could stop at the first page even when the named layer was
   later in the live catalog, and WMTS discovery did not independently fall
   back to WMS. The provider now searches the named layer and preserves the
   WMTS/WMS fallback contract.
7. The native map-session sanitizer discarded required nested raster render
   descriptor fields, including provider identity and temporal defaults, which
   left an unresolved `{time}` placeholder in the served tile template. The
   nested descriptor is now preserved and populated with the AEGIS proxy
   contract. Trace exposure checkpoints also retain integer iteration values.
8. The browser harness counted catalog-returned capabilities as selected and
   missed the human-readable nighttime-lights label. Trace summarization and
   target capability correlation now report only selected/executed capabilities
   and recognize the actual rendered label.

## External/provider outcomes

### FEMA and ESA

The final FEMA standalone run recorded `transport_error` during the upstream
request with no upstream HTTP status or content type. The ESA target-boundary
rerun recorded the same category. The sanitized upstream hosts were
`hazards.fema.gov` and `services.terrascope.be`; the browser saw only AEGIS
proxy requests. These results do not prove an AEGIS URL or renderer defect.
The latest ESA browser attempt stopped before a target proxy request because of
a model-side raw-tool trajectory and is not used as provider evidence.

See [network-summary.json](network-summary.json) and
[backend-raster-diagnostics.log](backend-raster-diagnostics.log). Representative
screenshots are [FEMA](browser-final/screenshots/RASTER-LIVE-DIAGNOSTICS/fema_new_orleans.png)
and [ESA](browser-rerun/screenshots/RASTER-LIVE-DIAGNOSTICS/esa_worldcover_rome.png).

### NASA GIBS

The 11 passing cases each have target capability proxy responses with
`200 image/png`, MapLibre source and layer state, visible canvas pixels, NASA
GIBS attribution, and `render_observed`; direct GIBS browser traffic was zero.
The temporal canary observed `time=2026-09-28` on every NDVI target proxy
request. The Day/Night case observed its effective provider time
`2023-07-07`.

The fire case was intentionally not substituted. The live WMTS capabilities
contained `MODIS_Combined_Thermal_Anomalies_All`, `_Day`, and `_Night`, but not
the advertised `MODIS_Combined_Thermal_Anomalies_Fire`. AEGIS recorded provider
unavailability and prepared no map. Its [failure screenshot](gibs-matrix-final/screenshots/GIBS-RASTER-MATRIX/MODIS_Combined_Thermal_Anomalies_Fire.png)
is retained with the passing [SRTM](gibs-canary-nontemporal-final2/screenshots/GIBS-RASTER-MATRIX/SRTM_Color_Index.png)
and [temporal NDVI](gibs-canary-temporal-fixed4/screenshots/GIBS-RASTER-MATRIX/MODIS_Terra_NDVI_8Day.png)
examples.

The per-case network acceptance fields are in [network-summary.json](network-summary.json),
and sanitized run trajectories are in [gibs-trace-summaries.json](gibs-trace-summaries.json).

## Quality and delivery boundary

The focused regression set passed **251 tests**. The broader backend unit suite
reported **994 passed and 1 failed**; the single failure is the canonical
runtime-hygiene test because protected pre-existing `.ruff_cache` residue is
present. No cache residue was removed. Ruff passed for all modified source and
test files, and strict Pyright passed with zero diagnostics. Frontend production
source was unchanged.

The ignored local `API_KEYS.md` file was not read, copied, staged, committed, or
pushed. The user-owned `.gitignore` change remains unstaged.

Hosted CI is recorded after the implementation commit is pushed; this report's
`tested_source` field is deliberately a working-tree evidence marker until the
exact implementation SHA is known.
