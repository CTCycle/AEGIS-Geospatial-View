# Webcam Capability

Last updated: 2026-05-14

## Scope

Webcams and public cameras are `camera-network` capabilities. They are selected by the main agent when a user asks for visual confirmation, road condition, beach condition, ski condition, port view, airport view, or traffic camera context.

## Windy Webcams

Manifest: `app/resources/manifests/cameras/windy_webcams.json`

Provider key: `WINDY_WEBCAMS_API_KEY`

Official docs: https://api.windy.com/webcams/docs

Rules:

- Send the key from backend provider code using the `x-windy-api-key` header.
- Preview image URL tokens expire and must be refreshed when loading the page.
- Do not embed live feeds unless provider documentation or terms explicitly allow embedding.
- If embedding is not allowed or unknown, render camera metadata, allowed preview image, stale state, and official link only.
- A stale camera must not fail the whole camera layer.
- Missing credentials return `missing-credential` state from `/api/geospatial/cameras`.

## API Contracts

- `GET /api/geospatial/cameras?bbox=&provider=&camera_type=`
- `GET /api/geospatial/cameras/{camera_id}`
- `GET /api/geospatial/sources/windy_webcams/credential-status`

The provider supports normalized mocked camera payloads for deterministic contract testing and provider-backed camera detail lookup for the API contract.

Provider-backed camera detail lookup is required for `GET /api/geospatial/cameras/{camera_id}`. The backend resolves provider-prefixed IDs, fetches the matching provider result safely, and returns access-needed or not-found state instead of leaking provider errors.

## Public Camera Templates

Additional disabled templates exist for:

- DOT traffic cameras.
- Public transport cameras.
- Tourism webcams.
- Ski resort webcams.
- Port and airport webcams.
- Environmental monitoring cameras.

These templates are not normal toggles until an official feed URL, provider attribution, license, embedding permission, freshness policy, and runtime profile are configured.

Configured local/agency camera sources can be supplied through `LOCAL_OPEN_DATA_SOURCES` as a JSON object mapping capability IDs to official JSON source URLs or local files. Supported source payloads are GeoJSON `FeatureCollection` objects or `{ "cameras": [...] }` lists with latitude/longitude and official links.

## Rendering Rules

- Camera dots render only for permitted, renderable camera layers.
- Low-zoom camera clusters must preserve count, provider, stale, and access-needed state.
- Popups must show camera name, provider, stale state, preview when allowed, and official link fallback.
- Expired preview URLs are refreshed through the provider path; stale previews degrade to metadata and official links.
- Live embed surfaces remain disabled unless the provider explicitly grants embedding rights.
