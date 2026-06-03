# Reference Catalog

Last updated: 2026-06-02

## Purpose

`app/resources/catalog/reference` stores seedable static reference data that should not live in Python constants.

## Current Files

- `countries.json`
- `geospatial_layers.json`
- `gibs_tile_matrix_sets.json`
- `gibs_layer_defaults.json`

## Startup Behavior

1. The app creates relational schema first.
2. It loads reference catalog files.
3. It seeds only empty target reference tables.
4. Populated target tables are not reseeded or upserted during startup.
