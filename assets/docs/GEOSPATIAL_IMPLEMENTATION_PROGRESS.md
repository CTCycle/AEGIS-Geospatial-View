# Geospatial Implementation Progress

Last updated: 2026-05-12

This document records progress against the AEGIS Geographic Intelligence completion plan. It is intentionally factual: completed work is separated from remaining gaps so capability status stays truthful.

## Completed In This Increment

- Added implementation-status auditing to `server.services.geospatial.layer_auditor`.
  - Reports schema validity, runtime registration, provider fetch coverage, normalizer/cache/API/client/test coverage, and placeholder statuses.
  - Fails strict audit when a functional manifest is backed by placeholder statuses.
  - Fails strict audit when placeholder-backed or metadata-only capabilities are exposed as normal manual toggles.
- Updated placeholder-backed manifests and runtime profiles so ingestion-only or partial sources are not presented as fully functional normal toggles.
- Added TomTom traffic incident manifest and runtime profile coverage.
- Hardened TomTom traffic flow tiles behind a backend proxy so browser payloads do not expose the TomTom API key.
- Completed RainViewer radar behavior for metadata fetch, latest-frame tile payloads, 5-minute cache, stale fallback, empty state, timeout, and malformed payload handling.
- Added Geoapify live Places query normalization, category filtering, bbox/category caching, clustered-point payloads, empty result handling, and malformed payload handling.
- Hardened Overpass amenity group query mapping, public-rate-limit propagation, timeout handling, empty result handling, and clustered POI normalization.
- Expanded Open-Meteo renderer payloads with clicked-point/weather metadata, air pollutant symbols, and wind-arrow feature metadata.
- Completed OpenAQ provider key gating, API key header propagation, pollutant filters, cache behavior, empty result handling, and stale fallback.
- Improved Windy Webcams behavior.
  - Uses `WINDY_WEBCAMS_API_KEY` server-side only.
  - Sends `x-windy-api-key` from the backend fetcher.
  - Normalizes camera points from bbox search payloads.
  - Suppresses expired preview URLs.
  - Detects stale cameras from inactive status or old update timestamps.
  - Allows embeds only when provider payload explicitly permits embedding.
  - Camera popup shows provider, type, coordinates, update time, preview, stale badge, official link, and license-use warning.
- Improved GTFS handling.
  - Static ZIP parser normalizes stops, routes, agencies, calendars, and shape LineStrings.
  - Realtime parser normalizes vehicles, service alerts, trip updates, feed timestamp, and vehicle rendering freshness.
  - Stale realtime feeds preserve metadata but suppress vehicle rendering.
- Confirmed dataset ingestion support already covers source materialization, checksum validation, source timestamp records, CSV/GeoJSON normalization, invalid geometry dropping, spatial/text indexes, tile manifests, and health records.
- Added and expanded unit tests for implementation completeness, provider adapters, RainViewer, GTFS, ingestion surfaces, and manifest status truthfulness.

## Validation Evidence

The following checks passed after this increment:

- `.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict`
  - Result: 79 manifests, 0 errors.
- `.\app\server\.venv\Scripts\python.exe -m pytest -c app/server/pyproject.toml app/tests/unit/test_manifest_schema_v2.py app/tests/unit/test_provider_registry.py app/tests/unit/test_geospatial_plan_completion_surface.py app/tests/unit/test_geospatial_api_contracts.py app/tests/unit/test_agentic_geospatial_selection.py app/tests/unit/test_geospatial_implementation_completeness.py app/tests/unit/test_phase4_provider_adapters.py app/tests/unit/test_gtfs_providers.py app/tests/unit/services/geospatial -q`
  - Result: 84 passed.
- `npm run build`
  - Result: passed.
- `npm run test:e2e:geospatial`
  - Result: passed.

For Windows local runs, pytest was executed with `TEMP` and `TMP` pointed at a repository-local `.tmp_pytest` directory because the default user temp directory was not readable by pytest.

## Known Remaining Gaps

- Some raster/documented-service providers still return descriptor payloads rather than performing live service validation at request time. They are renderable, but not all have live timeout/malformed/stale tests.
- EEA, ESA, Eurostat NUTS, and some statistical join capabilities still need fuller provider-specific fetch/normalize/render tests before they should be treated as end-to-end complete.
- Dataset-ingestion sources such as Natural Earth, OpenAddresses, Overture, OurAirports, and local parcel templates correctly remain partial or ingestion-gated until real source material is materialized in an environment.
- GTFS live feed fetching remains adapter/configuration dependent; current work covers static ZIP parsing, realtime protobuf/decoded normalization, and freshness policy.
- Visual browser validation is currently scenario-catalog and smoke-test based. More screenshot/assertion depth is still needed for every layer family listed in the original plan.
- CI workflow coverage still needs a final pass to ensure every new audit and geospatial validation command runs in GitHub Actions.

## Next Work

Recommended next increments:

1. Add provider-specific live tests and descriptors for EEA noise, ESA WorldCover, Eurostat NUTS/statistical joins, and FRED metadata-only fallback.
2. Add screenshot-backed browser cases for RainViewer, TomTom incidents, Windy Webcams popup states, GTFS static/realtime layers, and high-density clustered points.
3. Extend CI to run strict manifest audit, backend geospatial suites, implementation completeness, client build, and geospatial browser smoke tests.
4. Materialize one dataset-ingestion fixture per major dataset family so ingestion-gated sources can be visually validated without relying on live downloads.
