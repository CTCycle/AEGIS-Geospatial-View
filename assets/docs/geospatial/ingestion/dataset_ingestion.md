# Dataset Ingestion

Last updated: 2026-06-02

## Scope

Downloaded or preprocessed datasets use `dataset-ingestion` manifests. The default runtime handles materialization, checksum validation, metadata recording, CSV and GeoJSON normalization, lightweight indexes, tile manifests, and source-health records.

Heavy GIS dependencies remain optional for shapefiles, rasters, Parquet, and advanced tile generation.

## Required Manifest Fields

Dataset-ingestion manifests must define:

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
- `validation.minFeatureCount`

They should also define checksum and bbox constraints when the source publishes them.

## Execution Pipeline

1. Download or copy raw source into `data/geospatial/raw/{provider}/{dataset}/`.
2. Verify checksum when available.
3. Record source metadata.
4. Normalize CSV point datasets and GeoJSON feature collections into deterministic GeoJSON.
5. Preserve unsupported heavy formats as raw artifacts and mark the run partial.
6. Drop invalid rows or invalid geometries and record warnings.
7. Validate minimum feature count and optional bbox constraints.
8. Build lightweight spatial and text indexes where applicable.
9. Write a tile manifest for downstream vector-tile generation.
10. Write source health with feature count, status, warnings, and ingest timestamp.

## Current Dataset Manifests

- Natural Earth admin boundaries
- U.S. Census cartographic boundaries
- Census ACS demographic joins
- Eurostat NUTS regions
- Overture Maps places
- OpenAddresses points
- local parcel template
- OurAirports airport CSV

## Optional Heavy Dependencies

Use the optional `geospatial-ingestion` extra for packages such as GeoPandas, Rasterio, Pyogrio, DuckDB, and Rtree. Do not add them to the default backend dependency set unless required by the default runtime.
