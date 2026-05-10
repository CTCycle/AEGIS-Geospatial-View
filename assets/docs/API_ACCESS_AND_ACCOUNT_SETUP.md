# API Access and Account Setup Guide

Last updated: 2026-05-11

## Purpose

This guide lists the external services used by the AEGIS geospatial layer catalog and explains how to activate full coverage. Free/open providers remain enabled where no key is required. Credentialed providers stay unavailable until credentials are configured in the Access settings page or through environment variables.

Store secrets only through the encrypted credential repository or local environment variables. Do not commit API keys, tokens, `.env` files, shell history, screenshots, or provider dashboard exports.

## Credential Configuration

Preferred setup:

1. Open the AEGIS Access settings page.
2. Add the provider credential with label `api_key`.
3. Restart the backend if the credential is also used by long-running background services.
4. Rebuild vectors after changing provider coverage so agent retrieval reflects the active catalog.

Environment fallback:

| Provider | Environment variable | Required for full coverage |
| --- | --- | --- |
| ArcGIS private services | `ARCGIS_API_KEY` | Only for private/credentialed ArcGIS portals |
| Census | `CENSUS_API_KEY` | Optional for higher-volume Census API usage |
| FRED | `FRED_API_KEY` | Yes |
| Geoapify | `GEOAPIFY_API_KEY` | Yes |
| Google Maps Platform | `GOOGLE_MAPS_API_KEY` | Yes |
| NASA Open APIs | `NASA_API_KEY` | Optional for NASA API-backed endpoints, not required for public GIBS tiles |
| NREL AFDC | `NREL_API_KEY` | Yes, when AFDC station capabilities are enabled |
| OpenAQ | `OPENAQ_API_KEY` | Yes |
| OpenAIP | `OPENAIP_API_KEY` | Yes, when aviation capabilities are enabled |
| Open Charge Map | `OPENCHARGEMAP_API_KEY` | Depends on usage tier and endpoint |
| OpenTripMap | `OPENTRIPMAP_API_KEY` | Yes, when tourism POI capabilities are enabled |
| Sentinel Hub | `SENTINEL_HUB_CLIENT_ID`, `SENTINEL_HUB_CLIENT_SECRET` | Yes, when Sentinel Hub raster capabilities are enabled |
| TomTom | `TOMTOM_API_KEY` | Yes |
| Transitland | `TRANSITLAND_API_KEY` | Yes, when Transitland feed discovery is enabled |
| Windy Webcams | `WINDY_WEBCAMS_API_KEY` | Yes, when webcam capabilities are enabled |

## Providers

### OpenStreetMap and Overpass

Use: POI and amenity discovery through OSM tags.

Setup:

1. No account is required for the default public Overpass flow.
2. Review the [Overpass API documentation](https://wiki.openstreetmap.org/wiki/Overpass_API).
3. Keep queries bounded by location and radius.
4. Respect ODbL attribution and public instance usage policies.

Limits and restrictions:

- Public Overpass instances are shared infrastructure and can reject large or frequent queries.
- Use a private Overpass instance for production bulk workloads.

### Geoapify

Use: optional enhanced POI and OSM-derived map tiles.

Setup:

1. Create an account at [Geoapify](https://www.geoapify.com/).
2. Create or copy an API key from the Geoapify dashboard.
3. Configure `GEOAPIFY_API_KEY` or add a Geoapify `api_key` credential in Access settings.
4. Review the [Places API documentation](https://apidocs.geoapify.com/docs/places/) and [pricing](https://www.geoapify.com/pricing/).

Limits and restrictions:

- Free plans use daily credits and rate limits.
- Places API credit cost depends on requested result count.
- Confirm commercial-use rights before production deployment.

### TomTom

Use: optional road basemap and traffic flow layers.

Setup:

1. Create a TomTom developer account.
2. Follow [TomTom API key setup](https://docs.tomtom.com/platform/documentation/my-tomtom/how-to-get-a-tomtom-api-key/).
3. Copy the key from MyTomTom.
4. Configure `TOMTOM_API_KEY` or add a TomTom `api_key` credential in Access settings.
5. Review [API key management](https://docs.tomtom.com/platform/documentation/my-tomtom/api-key-management) and product quotas.

Limits and restrictions:

- Traffic coverage and refresh cadence vary by country and product.
- Evaluation/free access is limited; confirm production licensing.

### Open-Meteo

Use: weather forecasts, air-quality forecasts, pressure, humidity, wind, precipitation, and related time-series insights.

Setup:

1. No API key is required for the default public flow.
2. Review [Open-Meteo forecast API documentation](https://open-meteo.com/en/docs).
3. Keep requests location-bounded and request only required variables.

Limits and restrictions:

- Confirm non-commercial and high-volume limits before production use.
- Attribution is required where provider terms require it.

### OpenAQ

Use: air-quality station observations and measurements.

Setup:

1. Register for OpenAQ Explorer.
2. Follow [OpenAQ API key instructions](https://docs.openaq.org/using-the-api/api-key).
3. Configure `OPENAQ_API_KEY` or add an OpenAQ `api_key` credential in Access settings.
4. Send the key in the `X-API-Key` header in direct API integrations.

Limits and restrictions:

- Coverage depends on station networks and available public data.
- Observe rate-limit headers and avoid repeated 429 responses.

### NASA GIBS

Use: satellite imagery, land-surface temperature, precipitation, aerosols, ozone, NDVI, fire, nighttime lights, and terrain relief.

Setup:

1. No API key is required for default WMS/WMTS access.
2. Review [NASA GIBS APIs](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api).
3. Use layer-specific dates, CRS, and image sizes validated by the GIBS runtime.

Limits and restrictions:

- Layers have different temporal cadences and native resolutions.
- Some products are imagery/raster-only and are not machine-queryable vectors.

### NASA Open APIs

Use: optional NASA API-backed endpoints where a specific NASA service requires or benefits from a key. Public GIBS WMS/WMTS layers do not require this key.

Setup:

1. Request a key from [NASA Open APIs](https://api.nasa.gov/).
2. Configure `NASA_API_KEY` only for NASA API-backed capabilities that declare `auth.providerKey` as `nasa`.
3. Keep public GIBS manifests configured with `auth.type` set to `none`.

Limits and restrictions:

- NASA service quotas vary by API.
- Do not store NASA keys in manifests; manifests store only the provider key name.

### Windy Webcams

Use: optional webcam network capability with camera locations, preview images, timelapses, and official links.

Setup:

1. Review the [Windy Webcams API documentation](https://api.windy.com/webcams/docs).
2. Configure `WINDY_WEBCAMS_API_KEY` or add a Windy Webcams `api_key` credential in Access settings.
3. Send the key with the `x-windy-api-key` header from backend provider clients.

Limits and restrictions:

- Preview image URL tokens expire and must be refreshed when loading the page.
- Do not embed live feeds unless provider terms explicitly allow it.
- If embedding is not allowed or unknown, render metadata, allowed preview images, and the official link only.

### GTFS Realtime

Use: optional transit updates for trip updates, service alerts, and vehicle positions.

Setup:

1. Review the [GTFS Realtime documentation](https://developers.google.com/transit/gtfs-realtime).
2. Configure feed-specific credentials only when an agency requires them.
3. Parse GTFS Realtime payloads as Protocol Buffers over HTTP.

Limits and restrictions:

- Feed access, licensing, and freshness are agency-specific.
- Vehicle positions must not be displayed when the feed license or freshness policy does not support live vehicle rendering.

### ESA WorldCover

Use: global land-cover and land-use context through WMTS.

Setup:

1. No API key is required for the current WorldCover manifest.
2. Review [ESA WorldCover data access](https://esa-worldcover.org/en/data-access).
3. Keep ESA/Terrascope attribution visible in rendered maps.

Limits and restrictions:

- WorldCover is thematic raster/WMTS data; use it for visualization and classification context, not raw feature geometry.

### EEA

Use: EU/EEA environmental noise layers.

Setup:

1. No API key is required for public EEA services.
2. Review the [EEA Datahub](https://www.eea.europa.eu/en/datahub).
3. Verify service availability and licensing before operational use.

Limits and restrictions:

- Coverage is EU/EEA-focused.
- Noise layers are dataset-year specific.

### U.S. Census Bureau

Use: U.S. Census Data API and TIGERweb GeoServices for demographics, administrative boundaries, hydrography, and regional context.

Setup:

1. Review the [Census API user guide](https://www.census.gov/data/developers/guidance/api-user-guide.html).
2. Review [TIGERweb REST documentation](https://www.census.gov/data/developers/data-sets/TIGERweb-map-service.html).
3. Use public TIGERweb ArcGIS REST endpoints without a key for map geometry.
4. Request a Census API key for higher-volume statistical data access.
5. Configure `CENSUS_API_KEY` only when using key-backed Census Data API requests.

Limits and restrictions:

- Coverage is U.S.-only.
- TIGERweb geometry and Census statistical data use separate APIs and must be joined by geography codes.

### Eurostat

Use: EU/EEA demographic, housing, rent, and economic indicators.

Setup:

1. No account is required for public API access.
2. Review [Eurostat API introduction](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction).
3. Use dataset-specific API URLs and JSON-stat responses.

Limits and restrictions:

- Coverage is EU/EEA-focused and dataset-dependent.
- Eurostat API results are statistical time series, not map geometries by themselves.

### FRED

Use: U.S. economic, housing, rent, and market indicators.

Setup:

1. Create or log in to a FRED account.
2. Follow [FRED API key documentation](https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html).
3. Configure `FRED_API_KEY` or add a FRED `api_key` credential in Access settings.
4. Review series ownership and usage restrictions before redistribution.

Limits and restrictions:

- FRED data is time-series data, not direct map geometry.
- Some series have third-party copyright restrictions.

### ArcGIS REST Services

Use: public and credentialed ArcGIS FeatureServer/MapServer layers that can expose GeoJSON or map services.

Setup:

1. Review [ArcGIS REST output formats](https://developers.arcgis.com/rest/services-reference/enterprise/output-formats/).
2. Prefer FeatureServer query endpoints with `f=geojson` for vector-friendly layers.
3. Configure `ARCGIS_API_KEY` only for private or credentialed portals.
4. Validate `maxRecordCount`, geometry support, and service attribution before adding a manifest.

Limits and restrictions:

- Not every ArcGIS service supports GeoJSON.
- Services with M-values or restrictive query settings may reject `f=geojson`.

### Google Maps Platform

Use: credentialed commercial Places and geocoding metadata where policy permits.

Setup:

1. Create a Google Cloud project and enable billing.
2. Enable the required Google Maps Platform APIs.
3. Review [Places API usage and billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing).
4. Create and restrict an API key.
5. Configure `GOOGLE_MAPS_API_KEY` or add a Google Maps `api_key` credential in Access settings.

Limits and restrictions:

- Billing is required.
- Field masks affect cost and should be minimized.
- Google data has display and caching restrictions; do not add layers unless the use case complies with Google Maps Platform terms.

## Provider Exclusions

Zillow is not configured as a normal layer provider. Zillow API access is restricted to approved/license-backed use cases and is not suitable for guaranteed free/default data-layer coverage. Add it only if a licensed integration agreement exists and the usage terms are documented in the manifest.
