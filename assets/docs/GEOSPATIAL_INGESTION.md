# Geospatial Ingestion

Last updated: 2026-05-11

## Scope

Downloaded or preprocessed datasets use `dataset-ingestion` manifests. Heavy GIS dependencies are not part of the default runtime; ingestion planning and validation are available first, with processing implementations added behind optional extras.

## Manifest Contract

Dataset ingestion manifests must define:

- `download.sourceUrl`
- `download.license`
- `download.updateFrequency`
- `download.expectedFormat`
- `download.compression`
- `storage.rawPath`
- `storage.normalizedPath`
- `storage.tilePath`
- `normalization.targetCrs`
- `indexing.spatialIndex`
- `indexing.textIndex`
- `indexing.vectorTile`

The backend helper `build_ingestion_plan()` in `app/server/services/geospatial/ingestion.py` validates these fields and returns a normalized storage and indexing plan.

## Pipeline Stages

1. Download raw source.
2. Verify checksum if one is published.
3. Record source timestamp.
4. Normalize CRS.
5. Normalize field names.
6. Repair or drop invalid geometries with logged warnings.
7. Build spatial index.
8. Build text index where text fields exist.
9. Generate vector or raster tiles when required.
10. Write source health.
11. Run visual smoke validation.

## Optional Heavy Dependencies

Use an optional `geospatial-ingestion` extra for packages such as GeoPandas, Rasterio, Pyogrio, DuckDB, or tile-generation tools. Do not add these to the default backend dependency set unless the default runtime needs them.
