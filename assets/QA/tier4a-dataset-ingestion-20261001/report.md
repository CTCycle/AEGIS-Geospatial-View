# Tier 4A dataset-ingestion validation

Date: 2026-10-01
Branch: `validation`
Validated source: `validation@ee6c36bf` (clean working tree; equals `develop` at the same SHA)
Test environment: `app/server/.venv`, isolated pytest basetemp under
`runtimes/cache/pytest-tmp/t4a-20261001`; no runtime database or user data used.

## Scope

This is the first opened Tier 4A campaign slice. It establishes the T4A
ID-to-scenario mapping and validates the deterministic dataset-ingestion
implementation (CSV/GeoJSON materialization, checksums, indexes, health,
materialization filtering, GTFS static/realtime, catalog-only descriptors)
with isolated fixture data. It also probes the durable rollback/cleanup
boundary called out in the project-status ledger.

## Evidence

| Check | Result | Evidence file |
| --- | --- | --- |
| Focused ingestion/GTFS/live-validator suite | `24 passed` | `focused-suite.log` |
| Render-descriptor / geospatial API contract suite | `81 passed` (2 existing dependency warnings) | `descriptor-api-suite.log` |
| Strict production layer auditor | 86 manifests, `error_count=0`, `warning_count=0` | `strict-audit.log` |
| Configured-source materialization (6 fixture manifests) | All functional health, correct feature counts, normalized GeoJSON, indexes, tile manifests | `configured-source-materialization.json` |
| Rollback/cleanup boundary probe | Failures raise but leave partial artifacts; heavy formats return partial health | `rollback-cleanup-probe.json` |

The configured-source probe materialized `census_cartographic_boundaries`,
`local_parcel_template`, `natural_earth_admin_boundaries` (1 feature each),
`openaddresses_points`, `ourairports_airports` (2 features each), and
`overture_maps_places` (1 feature) through the real
`materialize_datasets` runner, each producing `healthStatus=functional`
with normalized GeoJSON, spatial/text indexes, and a tile manifest.

Optional `geospatial-ingestion` dependencies (geopandas, rasterio, pyogrio,
duckdb, rtree) are NOT installed in the validation environment, so the
heavy-format path is validated only as the designed fail-closed partial
result (raw artifact + `health.status=partial` with a warning), not as a
successful shapefile/parquet materialization.

## Rollback/cleanup boundary finding

`execute_ingestion_plan` (app/server/services/geospatial/ingestion.py)
creates the storage directories and materializes the raw source before
validation. When checksum mismatch, `minFeatureCount`, or
`bboxMustIntersect` validation rejects the run, the function raises
`IngestionExecutionError` but does not remove the already-written raw,
metadata, or normalized artifacts. The probe recorded:

- checksum mismatch: raw source file retained
- minFeatureCount rejection: raw + metadata + normalized GeoJSON retained
- bbox non-intersection: raw + metadata + normalized GeoJSON retained
- heavy format: returns a partial result (not an error) with a warning and
  `health.status=partial`, retaining raw + metadata + tile manifest
- unsupported source scheme: fails before writing anything

This is recorded as a validated limitation. No product change was made in
this slice (per scope decision); a durable rollback/cleanup contract for
failed materializations remains open and should be decided as a follow-up.

## T4A ID-to-scenario mapping and classification

| Slice | Established scenario | Status | Evidence boundary |
| --- | --- | --- | --- |
| `T4-01` | CSV ingestion: normalization, checksums, indexes, health | `PASS` | Fixture/manifest materialization of `openaddresses_points` and `ourairports_airports`; focused suite |
| `T4-02` | GeoJSON ingestion: normalization, invalid-geometry dropping, bbox | `PASS` | Fixture/manifest materialization of `natural_earth_admin_boundaries`, `census_cartographic_boundaries`, `overture_maps_places`, `local_parcel_template`; focused suite |
| `T4-03` | Optional heavy formats: shapefile/parquet/raster | `PARTIAL` | Fail-closed partial path validated; successful heavy-format materialization requires the optional `geospatial-ingestion` extra, which is not installed |
| `T4-04` | Mobility data: GTFS static/realtime | `PARTIAL` | Deterministic GTFS static parse and realtime tests pass; live configured feed URL is unavailable in this environment |
| `T4-05` | Local/configured sources | `PARTIAL` | Local fixture source materialization passes; configured external/local datasets (parcel, Overture index, OCM snapshot) are not configured |
| `T4-06` | Cameras (local/configured) | `BLOCKED` | No configured local camera sources/feeds available |
| `T4-07` | Credentialed providers (OpenAQ, TomTom, OpenTripMap, NASA FIRMS, OpenChargeMap) | `BLOCKED` | No approved credentials available; live validator reports skip |
| `T4-08` | Catalog-only descriptors | `PASS` | Render-descriptor and geospatial API contract suites pass for the descriptor boundary; strict auditor passes |

## Boundary

This slice proves the deterministic, isolated dataset-ingestion contract and
records the rollback/cleanup limitation. It does not validate live configured
external datasets, camera feeds, credentialed providers, browser rendering of
materialized layers, or successful optional heavy-format materialization.
`T4-03`, `T4-04`, `T4-05` remain `PARTIAL`; `T4-06` and `T4-07` remain
`BLOCKED` on missing configured sources/credentials. These are environment
and product-scope boundaries, not evidence of a repository defect.

## Cleanup

The isolated pytest basetemp was left under `runtimes/cache/pytest-tmp/t4a-20261001`;
no runtime database, settings, or provider credentials were used or modified.