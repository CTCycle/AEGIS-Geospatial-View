# Access Overview

Last updated: 2026-08-27

## Purpose

This file covers credential handling, provider-setup boundaries, and provider exclusions.

## Credential Configuration

Preferred flow:

1. Open the Access settings page.
2. Add the provider credential with label `api_key`.
3. Return to the geodata or workspace page; provider availability is resolved
   from the current credential and runtime profile.

Model-provider credentials are managed separately in Model Settings. Geospatial
agent visibility is catalog-based and does not require rebuilding embeddings.

## Resolution Semantics

`app/server/services/geospatial/credential_resolver.py` is the single
credential-resolution boundary used by provider adapters, the geospatial API,
agent discovery/rendering, and runtime status reporting.

Resolution is strict:

1. Look up the active encrypted database credential for the provider and label.
2. Decrypt and validate the saved value; mark it used when the caller requests
   usage tracking.
A saved credential that is empty or cannot be decrypted is an error condition;
the resolver does not silently fall back to a second secret source. Credential
values never enter manifests, API responses, provider payloads, browser logs,
or map snapshots.

Credentialed provider requests remain server-mediated: credentials are sent in
request headers or used to construct an internal proxy request, never exposed
in a frontend URL, render descriptor, or public provider payload.

Non-secret deployment configuration variables include:

- `LOCAL_OPEN_DATA_SOURCES`
- `AEGIS_MOBILITY_DATABASE_CATALOG_PATH` (optional local CSV snapshot override)

`LOCAL_OPEN_DATA_SOURCES` maps trusted source IDs to HTTPS URLs or local files.
The runtime accepts a configured source ID rather than an arbitrary caller URL,
and rejects private or loopback network targets.

## Secret Safety Rules

- Store secrets only through encrypted credential storage in AEGIS Access settings.
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
