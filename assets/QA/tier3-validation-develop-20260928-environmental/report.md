# GEO-FOCUS-16 environmental capability follow-up

Status: `PARTIAL`

Date: 2026-09-28

Tested implementation commit: `87ca6942`

## Why this slice was selected

The current ledger identified GEO-FOCUS-16 as an actionable keyless-capability
leftover covering EEA environmental noise and PVGIS solar potential. These two
requests form a bounded environmental slice with complementary failure
boundaries: PVGIS is metadata-only and should complete as text, while EEA is a
public raster path that requires browser-authoritative MapLibre evidence.

## Findings and fixes

The original PVGIS browser request could select an unrelated MODIS fire raster
after discovery, and the PVGIS response was persisted as an `unknown` result
even when the live payload contained a numeric estimate. The implementation
now:

- marks PVGIS as direct-text only (`supports_map=false`);
- maps `estimate` operations to the manifest's `show`/`inspect` primitives;
- adds bounded PVGIS/solar/photovoltaic semantic phrase matching so unrelated
  raster capabilities are excluded;
- normalizes an accidental map/both PVGIS route back to a text route; and
- classifies successful PVGIS responses as metadata and projects the bounded
  annual estimate into the model-facing execution summary.

No provider, model, or fallback lane was substituted.

## Verification

- Focused routing, manifest, execution-summary, provider-adapter, and PVGIS
  regression suite: **85 passed**.
- Ruff on all changed Python files: **passed**.
- Strict production manifest audit: **86 manifests, 0 errors, 0 warnings**.
- Exact-lane browser PVGIS request: location, capability selection, provider
  execution, metadata classification, numeric summary, and final text response
  all completed. The visible result was approximately **1,267
  kWh/kWp/year** for Rome, explicitly marked as a metadata-only point insight.
- Exact-lane browser EEA request: location clarification, capability selection,
  and provider execution completed. The provider returned an attributed,
  renderable raster descriptor, but MapLibre failed to load the public source;
  no raster pixels or accepted render acknowledgement were obtained.
- Hosted CI run [36480878494](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36480878494)
  passed all four jobs for the pushed documentation/source revision.

See [slice manifest](slice.json), [browser evidence](browser-evidence.md),
[live evidence](live-evidence.json), [focused suite](focused-suite.log), and
[quality checks](quality-checks.log).

## Final classification

The PVGIS portion is `PASS`. The EEA portion is `PARTIAL`: routing and provider
retrieval pass, while the public raster source/load boundary fails in the
browser. The EEA run also stopped after invalid recovery tool calls, so
`agent.map-render-ack-recovery` remains `PARTIAL`. This evidence does not close
`ISSUE-002`, `T3-07`, or the broader unrun Tier 3 rows.
