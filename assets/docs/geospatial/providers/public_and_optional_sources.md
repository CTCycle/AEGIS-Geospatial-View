# Public And Optional Sources

Last updated: 2026-08-02

## Canonical POI path

Overture Places is the primary bulk POI source after local ingestion into the configured GeoJSON index (`AEGIS_OVERTURE_PLACES_INDEX`). Interactive requests are bounded by bounding box, category, query, and limit. Overpass can be requested as an augmentation source with `augment_overpass=true`; results are normalized and deduplicated through the shared POI model.

Geoapify amenities and OpenTripMap tourism POIs remain available while representative-location parity benchmarks are incomplete. Removal requires the benchmark report to meet its recall, precision, completeness, and duplicate-rate thresholds.

Provider health is evaluated independently of catalog declaration. A timeout,
rate limit, malformed payload, or unavailable upstream is reported as a warning
or unavailable source; it is never promoted to a successful empty POI layer.

Run `python -m server.services.geospatial.poi_benchmark --baseline <provider-payload.json> --candidate <overture-or-overpass-payload.json> --output assets/QA/poi_parity_report.json` against captured representative-location payloads. The command returns success only when all configured parity thresholds pass.

## Public Sources

### OpenStreetMap And Overpass

Use for POI and amenity discovery through OSM tags.

- No account is required for the default public flow.
- Keep queries bounded by location and radius.
- Respect ODbL attribution and public instance limits.

### Open-Meteo

Use for weather and air-quality forecasts.

- No API key is required in the default flow.
- Request only required variables.
- Confirm high-volume and commercial-use limits before production scale.

### NASA GIBS

Use for satellite imagery and thematic earth-observation layers.

- No API key is required for public WMS or WMTS access.
- Discover live layers from WMS/WMTS XML capabilities through `NASAGIBSProvider`.
- Prefer WMTS render descriptors for tiled MapLibre rendering; use WMS only as fallback.
- Preserve layer time dimensions and default time values in render descriptors.
- Some products are raster-only and not machine-queryable vectors.

### GTFS Realtime

Use for transit updates, alerts, and vehicle positions.

- Feed-specific credentials are required only when an agency requires them.
- Parse payloads as Protocol Buffers over HTTP.
- Respect agency licensing and freshness rules.

### ESA WorldCover

Use for global land-cover context.

- No API key is required for the current manifest.
- Keep ESA and Terrascope attribution visible.

### EEA

Use for EU or EEA environmental noise layers.

- No API key is required for public services.
- Verify service availability and licensing before operational use.

## Optional Credentialed Sources

### Geoapify

Use for optional amenities overlays; OpenFreeMap and native OpenStreetMap styles provide the public basemap path.

- Configure `GEOAPIFY_API_KEY` or Access credentials.
- Review Places API quotas and pricing.
- Confirm commercial-use rights before production deployment.

### TomTom

Use for optional traffic flow and incident layers; it is no longer a basic basemap source.

- Configure `TOMTOM_API_KEY` or Access credentials.
- Coverage and refresh cadence vary by region.
- Confirm evaluation and production licensing.

### OpenAQ

Use for air-quality station observations and measurements.

- Configure `OPENAQ_API_KEY` or Access credentials.
- Send the key with `X-API-Key`.
- Respect rate-limit headers.

### OpenTripMap

Use for tourism-oriented points of interest.

- Configure `OPENTRIPMAP_API_KEY` or Access credentials.
- Keep requests bounded by location and radius.
- If the key is missing, the source should remain unavailable and public alternatives should be preferred.

### Open Charge Map

Use for EV charging station discovery.

- Hosted requests require `OPENCHARGEMAP_API_KEY`; anonymous hosted access is not treated as reliable.
- Prototype local snapshots with `AEGIS_OCM_SNAPSHOT_PATH` for bounded, keyless reads.
- Bound requests by viewport, radius, and result count.
- Cache station metadata and degrade gracefully on stale or empty results.

### NREL AFDC

Use for U.S. alternative fuel station discovery.

- Configure `NREL_API_KEY` or Access credentials.
- Prototype official current-data snapshots with `AEGIS_AFDC_SNAPSHOT_PATH`; keep the hosted API credential-gated until freshness and schema parity are validated.
- Use bounded searches only.
- Keep fuel type, access, and station status visible in normalized metadata.

### NASA Open APIs

Use for NASA API-backed capabilities that are distinct from public GIBS tiles.

- Configure `NASA_API_KEY` only when a capability explicitly requires it.
- Public GIBS manifests should keep `auth.type` as `none`.

### Google Maps Platform

Use for policy-compliant commercial Places or geocoding metadata.

- Billing is required.
- Minimize field masks because they affect cost.
- Do not add layers unless the use case complies with Google Maps Platform terms.
