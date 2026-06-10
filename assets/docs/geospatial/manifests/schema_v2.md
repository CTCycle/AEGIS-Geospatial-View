# Schema V2

Last updated: 2026-06-02

## Required Fields

Every manifest under `app/resources/catalog` must define:

- `capabilityKind`
- `renderingMode`
- `sourceOfficialDocs`
- `license`
- `auth`
- `reliability`
- `cachePolicy`
- `normalization`

Optional but supported fields include:

- `account_setup`
- `agenticUse`

## Supported Values

`capabilityKind` must be one of:

- `basemap`
- `raster-overlay`
- `vector-overlay`
- `search-index`
- `camera-network`
- `dataset-ingestion`
- `analysis-tool`
- `metadata-only`

`renderingMode` must be one of:

- `xyz`
- `wmts`
- `wms`
- `geojson`
- `vector-tile`
- `raster-tile`
- `clustered-points`
- `choropleth`
- `camera-points`
- `metadata-only`

## Strict Rules

- Credential-gated manifests must set both `auth.providerKey` and `auth.accessPageProviderId`.
- Manifests must never contain raw secrets, tokens, or API keys.
- `account_setup.credential_fields` may contain access keys or tokens only, not portal usernames or passwords.
- Renderable capabilities must declare supported rendering mode and normalization geometry.
- Metadata-only and analysis-tool capabilities cannot masquerade as successful empty geometry payloads.

## Account Setup Metadata

`account_setup.automation.support` must be one of:

- `manual_only`
- `guided_playwright`
- `agent_assisted`
- `unsupported`

Automation metadata must never request storage of provider passwords, CAPTCHA responses, 2FA codes, recovery codes, or billing credentials.

## Audit Command

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict
```
