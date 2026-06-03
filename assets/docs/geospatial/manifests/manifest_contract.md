# Manifest Contract

Last updated: 2026-06-02

## Loader Contract

- Providers, basemaps, overlays, and direct tools are loaded through `GeospatialManifestLoader`, `CapabilityRegistry`, and `RuntimeRegistry`.
- Capability manifests are the source of truth for agent catalog, describe, and execute operations.
- Capability IDs must remain stable because the agent executes by `capability_id`.
- Runtime availability is controlled by `runtime_profiles.json` plus credential presence.

## Metadata Expectations

Every capability must define:

- purpose
- data source
- update frequency
- access constraints
- dependencies

Every metadata object must expose:

- `official_docs_url`
- `source_protocol`
- `data_format`
- `geometry_type`
- `queryable`
- `vectorizable`
- `endpoint_health`
- `auth_mode`
- `rate_limit_notes`

## Behavior Rules

- Schema v2 is the only accepted manifest contract.
- Credential-backed providers use encrypted credential storage with environment fallback.
- Queryable and vectorizable claims are reserved for structured machine-readable sources.
- `metadata-only` capabilities must not claim renderable geometry.
- Disabled or broken layers must remain unavailable until manifest, runtime, credentials, and health allow rendering.
- OpenLayers-compatible source protocols are the manifest standard even though the current UI renderer is MapLibre.

## Maintenance Rules

- Additive capability work must update manifest JSON, `runtime_profiles.json`, tests, and docs together.
- Credential-required providers remain optional unless product policy changes.
- Default capability selection should favor free or open providers.
- UI pages should consume `/api/maps/catalog` instead of duplicating manifest parsing.
