# Access Overview

Last updated: 2026-06-02

## Purpose

This file covers credential handling, provider-setup boundaries, and provider exclusions.

## Credential Configuration

Preferred flow:

1. Open the Access settings page.
2. Add the provider credential with label `api_key`.
3. Restart the backend if the credential is used by long-running background services.
4. Rebuild vectors when provider coverage changes and agent retrieval should reflect it.

Environment fallback variables include:

- `ARCGIS_API_KEY`
- `CENSUS_API_KEY`
- `FRED_API_KEY`
- `GEOAPIFY_API_KEY`
- `GOOGLE_MAPS_API_KEY`
- `NASA_API_KEY`
- `NREL_API_KEY`
- `OPENAQ_API_KEY`
- `OPENAIP_API_KEY`
- `OPENCHARGEMAP_API_KEY`
- `OPENTRIPMAP_API_KEY`
- `SENTINEL_HUB_CLIENT_ID`
- `SENTINEL_HUB_CLIENT_SECRET`
- `TOMTOM_API_KEY`
- `TRANSITLAND_API_KEY`
- `WINDY_WEBCAMS_API_KEY`
- `LOCAL_OPEN_DATA_SOURCES`

## Secret Safety Rules

- Store secrets only through encrypted credential storage or local environment variables.
- Do not commit keys, tokens, `.env` files, shell history, screenshots, or provider dashboard exports.
- Credential-gated manifests must reference only provider key names and access-page provider IDs.
- Raw keys are prohibited in manifests, browser logs, provider responses, and snapshots.

## Guided Setup Boundary

The Access page exposes an experimental human-in-the-loop `Get API key` trigger for some providers.

AEGIS:

- may open portal or documentation links
- may show setup notes
- may guide the user through verified steps

AEGIS does not:

- create provider accounts autonomously
- collect provider passwords
- collect CAPTCHA responses
- collect 2FA or recovery codes
- collect billing credentials

If guided setup fails or is unsupported, the flow must degrade to manual instructions and official links.

## Automation Support Values

- `manual_only`
- `guided_playwright`
- `agent_assisted`
- `unsupported`

## Provider Exclusion

Zillow is excluded from the normal provider set. Add it only under a licensed integration with documented usage terms.
