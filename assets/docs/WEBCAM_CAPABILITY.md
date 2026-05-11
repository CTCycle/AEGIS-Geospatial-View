# Webcam Capability

Last updated: 2026-05-11

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

The current provider shell supports normalized mocked camera payloads for deterministic contract testing. Live Windy fetch implementation is the next provider-specific step.
