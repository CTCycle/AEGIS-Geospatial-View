# Geospatial Validation

Last updated: 2026-05-11

## Static Validation

Run from the repository root:

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict
```

The audit fails when any manifest omits schema-v2 fields, source docs, license, auth, reliability, cache policy, or normalization metadata.

## Backend Contract Tests

Focused geospatial tests:

```powershell
app\server\.venv\Scripts\python.exe -m pytest `
  app\tests\unit\test_manifest_schema_v2.py `
  app\tests\unit\test_provider_registry.py `
  app\tests\unit\test_phase4_provider_adapters.py `
  app\tests\unit\test_geospatial_api_contracts.py `
  app\tests\unit\test_agentic_geospatial_selection.py `
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

## Frontend Validation

Run:

```powershell
npm --prefix app/client run build
```

The current frontend contract validates TypeScript integration for schema-v2 types, geospatial API helpers, services, layer catalog, source health badge, camera popup, and map renderer dispatch.

## Browser Validation

Visual validation is still required before marking the full geographic intelligence program complete. Browser scenarios should cover:

- base map only
- missing credential states
- RainViewer/GIBS raster descriptors
- OpenAQ/Open-Meteo/Overpass mocked vector payloads
- Windy webcam missing-key and mocked camera payloads
- layer catalog filtering and source-health display
