# Geospatial Ingestion

Last updated: 2026-05-11

## Scope

Downloaded or preprocessed datasets use `dataset-ingestion` manifests. Heavy GIS dependencies are not part of the default runtime; the built-in ingestion path handles source materialization, checksum validation, metadata recording, CSV and GeoJSON normalization, lightweight spatial/text indexes, tile manifests, and health records. Shapefile, raster, Parquet, and advanced tile generation are gated behind optional GIS tooling.

## Manifest Contract

Dataset ingestion manifests must define:

- `download.sourceUrl`
- `download.license`
- `download.updateFrequency`
- `download.expectedFormat`
- `download.compression`
- `download.checksumUrl` or `download.checksumSha256` when the source publishes a checksum
- `storage.rawPath`
- `storage.normalizedPath`
- `storage.tilePath`
- `normalization.targetCrs`
- `indexing.spatialIndex`
- `indexing.textIndex`
- `indexing.vectorTile`
- `validation.minFeatureCount`
- `validation.bboxMustIntersect` when the source is expected to overlap a known operating extent

The backend helper `build_ingestion_plan()` in `app/server/services/geospatial/ingestion.py` validates these fields and returns a normalized storage and indexing plan. `execute_ingestion_plan()` executes that plan for local files, `file://` URLs, and HTTP(S) downloads.

## Pipeline Stages

1. Download or copy the raw source into `data/geospatial/raw/{provider}/{dataset}/`.
2. Verify SHA-256 checksum when `download.checksumSha256` is declared or when `download.checksumUrl` resolves to a SHA-256 digest.
3. Record source URL, timestamp, checksum, checksum source, expected format, compression, and target CRS.
4. Normalize CSV point datasets and GeoJSON feature collections into deterministic GeoJSON.
5. Preserve unsupported heavy formats as raw artifacts and mark the run partial until optional GIS tooling processes them.
6. Drop CSV rows with invalid or missing coordinates.
7. Drop GeoJSON features with invalid geometry and record warnings.
8. Validate minimum feature count and optional bbox intersection constraints.
9. Build a lightweight bbox spatial index when normalized geometry exists.
10. Build a term-to-feature text index where text fields exist.
11. Write a tile manifest for downstream vector tile generation.
12. Write source health with feature count, status, warnings, and ingest timestamp.
13. Run visual smoke validation after tiles or normalized GeoJSON are available.

## Current Dataset Manifests

- Natural Earth admin boundaries.
- US Census cartographic boundaries.
- Census ACS demographic joins.
- Eurostat NUTS regions.
- Overture Maps places.
- OpenAddresses points.
- Local parcel template.
- OurAirports airport CSV.

## Optional Heavy Dependencies

Use an optional `geospatial-ingestion` extra for packages such as GeoPandas, Rasterio, Pyogrio, DuckDB, or tile-generation tools. Do not add these to the default backend dependency set unless the default runtime needs them.
