## Reference Catalog Validation

Date: 2026-06-02

Validation performed:

- Removed `app/resources/database.db` and recreated it by starting the backend.
- Confirmed backend startup on `http://127.0.0.1:7059/docs`.
- Verified these tables were created and seeded on first startup:
  - `reference_countries`
  - `reference_country_aliases`
  - `reference_geospatial_layers`
  - `reference_geospatial_layer_aliases`
  - `reference_geospatial_layer_keywords`
  - `reference_gibs_tile_matrix_sets`
  - `reference_gibs_layer_defaults`
- Restarted the backend and confirmed row counts were unchanged.

Artifacts:

- `reference-counts-first.json`
- `reference-counts-second.json`
