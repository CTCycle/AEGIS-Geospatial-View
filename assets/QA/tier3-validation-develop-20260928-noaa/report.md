# T3-04 NOAA alert geometry remediation and validation

Status: `PASS`

Date: 2026-09-28

Tested implementation commit: `acf01a580166fc685eb5bde52f4e4cca2482d4a3`

## Scope

T3-04 covered the exact-lane NOAA live-alert boundary that was previously
`BLOCKED` after the active alert feed returned a feature with `geometry: null`
and the model stopped after invalid map-tool calls. The selected slice also
revisited the related renderer-admission and normalized-GeoJSON conversion
paths so the validation used the current implementation rather than only the
old ledger status.

## Finding and fix

The NOAA active-alert product can omit an alert polygon while exposing official
`affectedZones` links. The previous adapter preserved the alert but left its
normalized geometry empty, so the server correctly refused map admission. The
reliable implementation now:

- resolves only canonical `https://api.weather.gov/zones/forecast/{UGC}` links
  from provider-owned `affectedZones` and UGC data;
- skips unnecessary zone lookups when an alert already has usable geometry;
- bounds zone lookups to 32 and performs them concurrently;
- caches only valid normalized zone geometries for one day plus one day of
  stale-while-revalidate allowance;
- combines multiple affected-zone geometries into a GeoJSON
  `GeometryCollection`;
- reports a warning and `partial` result when a zone lookup is unavailable,
  while preserving the alert as data rather than claiming it rendered; and
- teaches map eligibility, bounds calculation, and render-data conversion to
  handle normalized non-`Feature` GeoJSON geometry dictionaries.

No fallback provider or alternate model was used.

## Verification

- Focused provider, capability, and map-builder suite: **29 passed**.
- Agent/map-plan regression slice: **96 passed**.
- Ruff: **All checks passed**.
- Strict Pyright: **0 errors, 0 warnings, 0 informations**.
- Fresh live `NOAAProvider` instance: `ok`, `partial=false`, one feature,
  `GeometryCollection` from `affected_zones`, no warnings.
- Exact OpenCode Go browser request: all four tool calls succeeded; the map
  visibly rendered the `NOAA Weather Alerts` GeoJSON layer with provider and
  MapLibre attribution; the trace recorded render observation and completed
  finalization.

See [browser evidence](browser-evidence.md), [API response](api-response.json),
[focused suite](focused-suite.log), [regression suite](regression-suite.log),
and [quality checks](quality-checks.log).

## Final classification

T3-04 is `PASS`. The earlier non-renderable-provider constraint is resolved by
provider-owned affected-zone geometry resolution and the normalized-geometry
renderer path. A future zone-fetch outage remains an explicitly `PARTIAL`
provider result and must not be promoted to a rendered success. Other NOAA
capabilities and the broader Tier 3 matrix remain separate validation scope.
