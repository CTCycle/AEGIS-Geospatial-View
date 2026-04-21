# Capability Manifests

Last updated: 2026-04-21

## Purpose

Capability manifests define extensible geospatial and direct-tool behavior without core workflow edits.

Manifests are loaded from `AEGIS/resources/manifests` through:
- `GeospatialManifestLoader`
- `CapabilityRegistry`
- `RuntimeRegistry`

## Index

`index.json` must define:
- `providers_dir`
- `basemaps_dir`
- `overlays_dir`
- `tools_dir`
- `runtime_profiles_file`

## Required Capability Fields

Each basemap/overlay/tool manifest entry must include:
- `id`
- `name`
- `provider`
- `type`
- `description`
- `capabilities`
- `coverage`
- `version`
- `last_modified`
- `metadata`

Tool manifests also require metadata used by policy/retrieval/runtime:
- `metadata.intent_tags`
- `metadata.task_tags`
- `metadata.search_examples`
- `metadata.handler_name`
- `metadata.requires_location`
- `metadata.supports_direct_text`
- `metadata.supports_map`

## Runtime Profiles

`runtime_profiles.json` contains `profiles[]` entries with:
- `capability_id`
- `enabled_by_default`
- `credential_provider`
- `supports_map`
- `supports_direct_text`
- `coverage_policy`
- `health_policy`
- `handler_name` (tools)

Every capability id from basemaps, overlays, and tools must have a runtime profile entry.

## Coverage Policies

Supported coverage values:
- `global`
- `global-partial`
- `eu-eea`
- `global-except-poles`

Coverage is enforced by `AEGIS/server/services/geospatial/coverage.py`.

## Adding a New Basemap

1. Add basemap manifest JSON in `basemaps/`.
2. Add matching runtime profile in `runtime_profiles.json`.
3. Rebuild/sync vector manifests.
4. Confirm catalog and retrieval include the capability.

## Adding a New Overlay

1. Add overlay manifest JSON in `overlays/`.
2. Add matching runtime profile entry.
3. Rebuild/sync vector manifests.
4. Confirm overlay appears in retrieval/ranking and catalog output.

## Adding a New Direct Tool

1. Add tool manifest JSON in `tools/`.
2. Add runtime profile with `handler_name`.
3. Implement handler in `AEGIS/server/services/agent/tool_handlers/`.
4. Register handler name in `ToolRegistry.load_tool_bindings()`.
5. Rebuild/sync vector manifests.
6. Verify direct-tool selection and execution.

## Required Tests for Capability Changes

When adding or changing capabilities, tests must cover:
- manifest completeness
- runtime profile completeness
- tool binding completeness (for tools)
- retrieval visibility for new capability without core policy/orchestrator edits
- coverage filtering behavior when applicable
