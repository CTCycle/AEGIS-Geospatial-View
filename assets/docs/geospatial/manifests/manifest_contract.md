# Manifest Contract

Last updated: 2026-09-08

## Loader Contract

- Providers, basemaps, overlays, and direct tools are loaded through `GeospatialManifestLoader`, `CapabilityRegistry`, and `RuntimeRegistry`.
- Capability manifests are the source of truth for agent catalog, describe, and execute operations.
- Capability IDs must remain stable because the agent executes by `capability_id`.
- Runtime availability is controlled by `runtime_profiles.json` plus the typed
  `availability_mode`. Supported modes are `public`, `credential`,
  `credential_or_local_source`, and `configured_source`; local source modes
  name a non-secret environment variable such as `AEGIS_OCM_SNAPSHOT_PATH`.

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

Executable capabilities also declare the provider-neutral execution contract:

- supported operations and analysis-scope kinds
- temporal modes and available windows
- required inputs
- normalized output and geometry type
- render support (`vector`, `raster`, `metadata_only`, or `none`)
- coverage, limitations, and semantically equivalent fallback IDs

Unknown metadata is treated as unknown support. The planner selects a manifest
by the canonical capability requirement and target scope; a provider name or
the existence of an upstream endpoint cannot expand the declared semantics.

## Behavior Rules

- Schema v2 is the only accepted manifest contract.
- Credential-backed providers use encrypted credential storage without environment fallback.
- API keys are resolved only through encrypted AEGIS Access storage. Source
  paths and feed URLs may use explicit non-secret configuration variables, but
  they must not be treated as API-key fallbacks.
- Queryable claims are reserved for structured machine-readable sources.
- `metadata-only` capabilities must not claim renderable geometry.
- A metadata-only or unavailable result cannot satisfy a required visual map
  completion requirement.
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
