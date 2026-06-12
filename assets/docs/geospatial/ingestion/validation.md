# Validation

Last updated: 2026-06-12

## Static Validation

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict --production
```

The audit fails on missing schema-v2 metadata, invalid geometry claims, unsafe secret-like values, or incomplete production coverage.

## Backend Contract Tests

Focused coverage includes:

- manifest schema-v2 loading
- provider registry binding
- timeout, retry, and circuit-breaker behavior
- provider payload normalization
- geospatial API contracts
- camera detail and missing-key behavior
- agentic selection and policy gates
- dataset-ingestion execution and validation
- hazard legends, freshness labels, and safe failure states

## Frontend Validation

```powershell
npm --prefix app/client run build
npm --prefix app/client test -- --watch=false --browsers=ChromeHeadlessNoGpu
```

Frontend validation covers schema-v2 types, geospatial API helpers, services, capability catalog behavior, source-health display, camera popup behavior, and renderer dispatch.

## Browser Validation

Major renderer changes require browser validation covering:

- basemap-only sessions
- missing-credential states
- raster descriptor rendering
- mocked vector payload rendering
- webcam missing-key and mocked camera payloads
- capability catalog filtering and source-health display

## CI And Live Validation

CI should run:

- strict auditor
- focused geospatial unit contracts
- client build and test suite
- geospatial browser-smoke command

Live-provider validation should run outside deterministic CI when network access is available:

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.live_validator --strict
.\server\.venv\Scripts\python.exe -m server.services.geospatial.live_validator --strict --include-credentialed
```
