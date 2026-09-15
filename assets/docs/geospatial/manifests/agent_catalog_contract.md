# Agent Catalog Contract

Last updated: 2026-09-15

## Stable Native Tools

The native registry exposes one internal route bootstrap plus the bounded
catalogue and execution tools:

- `route_request` (internal bootstrap)
- `resolve_geospatial_location`
- `discover_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `discover_geospatial_provider_layers` (only for explicitly routed
  provider-native discovery)
- `inspect_evidence`
- `transform_geospatial_evidence`
- `apply_map_plan`

## Tool Rules

- `discover_geospatial_capabilities` returns compact metadata only.
- Pagination must be deterministic.
- Page size is capped at 50.
- `describe_geospatial_capability` returns one full manifest descriptor plus executable argument schema.
- `execute_geospatial_capability` validates supplied arguments against the manifest schema before execution.
- `discover_geospatial_provider_layers` accepts only policy-allowed provider IDs
  and returns normalized descriptors, never raw provider XML or credentials.
- `inspect_evidence` returns bounded views of stored evidence and
  never returns an unrestricted payload.
- `transform_geospatial_evidence` accepts only declarative vector/tabular
  operations and persists a derived evidence record with parent provenance.
- `apply_map_plan` creates a candidate map only; browser render
  acknowledgement remains authoritative for visible completion.
- Native tool schemas reject undeclared top-level properties.

## Visibility Rule

The agent must not depend on embeddings, semantic retrieval, or vector ranking to decide which manifest tools are visible. Agent tool exposure is catalog-based.
