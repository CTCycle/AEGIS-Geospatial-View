# Public And Optional Sources

Last updated: 2026-06-02

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
- Use layer-specific dates, CRS, and image sizes validated by the GIBS runtime.
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

Use for optional polished basemaps and amenities.

- Configure `GEOAPIFY_API_KEY` or Access credentials.
- Review Places API quotas and pricing.
- Confirm commercial-use rights before production deployment.

### TomTom

Use for optional road basemap and traffic flow layers.

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

- Configure `OPENCHARGEMAP_API_KEY` when deployment volume or endpoint policy requires it.
- Bound requests by viewport, radius, and result count.
- Cache station metadata and degrade gracefully on stale or empty results.

### NREL AFDC

Use for U.S. alternative fuel station discovery.

- Configure `NREL_API_KEY` or Access credentials.
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
