# Geospatial Validation

Last updated: 2026-05-14

## Static Validation

Run from the repository root:

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict --production
```

The audit fails when any manifest omits schema-v2 fields, source docs, license, auth, reliability, cache policy, or normalization metadata. It also reports schema, provider, renderer, auth, and source-doc coverage; rejects metadata-only geometry claims; rejects normal toggles for broken layers; verifies credential-gated access setup IDs; and scans manifests for secret-like values.

The production audit additionally fails any non-provider capability with placeholder provider states, missing concrete provider fetch support, missing unit coverage, missing client renderer coverage, or missing browser scenario coverage.

## Backend Contract Tests

Focused geospatial tests:

```powershell
app\server\.venv\Scripts\python.exe -m pytest `
  app\tests\unit\test_geospatial_manifest_schema_v2.py `
  app\tests\unit\test_geospatial_layer_auditor.py `
  app\tests\unit\test_geospatial_manifest_secret_safety.py `
  app\tests\unit\test_geospatial_provider_contracts.py `
  app\tests\unit\test_geospatial_cache.py `
  app\tests\unit\test_geospatial_api_contracts.py `
  app\tests\unit\test_geospatial_api_credentials.py `
  app\tests\unit\test_geospatial_api_camera_detail.py `
  app\tests\unit\test_agentic_geospatial_selection.py `
  app\tests\unit\test_agentic_geospatial_policy_gates.py `
  app\tests\unit\test_agentic_geospatial_map_session.py `
  app\tests\unit\test_geospatial_ingestion.py `
  app\tests\unit\test_geospatial_ingestion_validation.py `
  app\tests\unit\test_geospatial_dataset_health.py `
  -q -p no:cacheprovider
```

Coverage includes:

- strict schema-v2 loading
- provider registry binding
- timeout, retry, and circuit breaker behavior
- provider adapter payload normalization
- camera missing-key behavior
- geospatial API contracts
- agentic selection for cameras, amenities, and no-layer general chat
- dataset ingestion plan execution for CSV/GeoJSON, checksum failure, lightweight indexes, and health artifacts
- camera permissions, staleness, and provider-backed detail lookup
- GTFS static and realtime parsing surfaces, including alerts and vehicle positions
- hazard legends, freshness labels, and provider-safe failure states
- POI deduplication, infrastructure source classification, and search-index output

## Frontend Validation

Run:

```powershell
npm --prefix app/client run build
npm --prefix app/client test -- --watch=false --browsers=ChromeHeadlessNoGpu
```

The current frontend contract validates TypeScript integration for schema-v2 types, geospatial API helpers, services, layer catalog, source health badge, camera popup, and map renderer dispatch.

## Browser Validation

Visual validation is required before releasing major renderer changes. Browser scenarios cover:

- base map only
- missing credential states
- RainViewer/GIBS raster descriptors
- OpenAQ/Open-Meteo/Overpass mocked vector payloads
- Windy webcam missing-key and mocked camera payloads
- layer catalog filtering and source-health display

`npm --prefix app/client run test:e2e:geospatial` now runs a focused ChromeHeadless/Karma browser smoke before validating the static scenario catalog. The smoke uses mocked API responses to exercise an OSM basemap session, a clustered GeoJSON layer, metadata-only layer state, Windy Webcams missing-credential messaging, and DOM/map-input checks for secret leakage. Playwright is not currently a client dependency; add it only when broader screenshot/browser-flow coverage is needed.

## CI Coverage

The CI workflow runs the strict auditor, focused geospatial unit contracts, the client build/test suite, and the geospatial browser-smoke scenario command. New capability work should add contract tests first and only expand live provider coverage through mocked, credential-safe fixtures.
