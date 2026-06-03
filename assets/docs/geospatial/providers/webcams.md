# Webcams

Last updated: 2026-06-02

## Scope

Webcams and public cameras are `camera-network` capabilities. They are used when a user asks for visual confirmation, traffic-camera context, beach views, ski conditions, airport views, port views, or similar live-scene requests.

## Windy Webcams

- Manifest: `app/resources/catalog/cameras/windy_webcams.json`
- Provider key: `WINDY_WEBCAMS_API_KEY`
- Official docs: `https://api.windy.com/webcams/docs`

Rules:

- Send the key from backend provider code using `x-windy-api-key`.
- Preview image URL tokens expire and must be refreshed when loading the page.
- Do not embed live feeds unless the provider explicitly allows embedding.
- When embedding is disallowed or unknown, render metadata, allowed preview images, stale state, and official links only.
- Missing credentials must surface `missing-credential` state from `/api/geospatial/cameras`.

## API Contracts

- `GET /api/geospatial/cameras?bbox=&provider=&camera_type=`
- `GET /api/geospatial/cameras/{camera_id}`
- `GET /api/geospatial/sources/windy_webcams/credential-status`

Provider-backed camera detail lookup is required for `GET /api/geospatial/cameras/{camera_id}`. The backend resolves provider-prefixed IDs safely and returns access-needed or not-found states instead of raw provider errors.

## Public Camera Templates

Disabled templates exist for:

- DOT traffic cameras
- public transport cameras
- tourism webcams
- ski resort webcams
- port and airport webcams
- environmental monitoring cameras

These templates remain disabled until feed URL, attribution, license, embedding permission, freshness policy, and runtime profile are configured.

## Rendering Rules

- Camera dots render only for permitted, renderable camera layers.
- Low-zoom clusters preserve count, provider, stale, and access-needed state.
- Popups show camera name, provider, stale state, preview when allowed, and official-link fallback.
- Expired previews are refreshed through the provider path.
