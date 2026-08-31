# Manifest Contract

Last updated: 2026-08-02

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
- `endpoint_health`
- `auth_mode`
- `rate_limit_notes`

## Behavior Rules

- Schema v2 is the only accepted manifest contract.
- Credential-backed providers use encrypted credential storage without environment fallback.
- Queryable claims are reserved for structured machine-readable sources.
- `metadata-only` capabilities must not claim renderable geometry.
- Disabled or broken layers must remain unavailable until manifest, runtime, credentials, and health allow rendering.
- Manifest source protocols are normalized into the backend render descriptor contract used by the MapLibre UI.
- Provider manifests may declare `live_layers_supported` and capability protocols for provider-native discovery. Discovered live layers are not written back into static manifests automatically.
- Curated overlays and live provider layers must use the same backend render descriptor contract before reaching `MapSession`.
- The loader requires `agenticUse` in every schema-v2 manifest even when its
  values disable agent exposure; optional behavior is expressed inside that
  required object rather than by omitting the field.

## Maintenance Rules

- Additive capability work must update manifest JSON, `runtime_profiles.json`, tests, and docs together.
- Credential-required providers remain optional unless product policy changes.
- Default capability selection should favor free or open providers.
- UI pages should consume `/api/geospatial/capabilities` instead of duplicating manifest parsing.
