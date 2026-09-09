# Agent Catalog Contract

Last updated: 2026-09-09

## Stable Native Tools

The agent accesses manifests through eight stable native tools:

- `resolve_geospatial_location`
- `list_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `fetch_geospatial_provider_layers` (only for explicitly routed provider-native discovery)
- `inspect_geospatial_evidence`
- `transform_geospatial_evidence`
- `prepare_geospatial_map`

## Tool Rules

- `list_geospatial_capabilities` returns compact metadata only.
- Pagination must be deterministic.
- Page size is capped at 50.
- `describe_geospatial_capability` returns one full manifest descriptor plus executable argument schema.
- `execute_geospatial_capability` validates supplied arguments against the manifest schema before execution.
- `fetch_geospatial_provider_layers` accepts only policy-allowed provider IDs and returns normalized descriptors, never raw provider XML or credentials.
- `inspect_geospatial_evidence` returns bounded views of stored evidence and
  never returns an unrestricted payload.
- `transform_geospatial_evidence` accepts only declarative vector/tabular
  operations and persists a derived evidence record with parent provenance.
- `prepare_geospatial_map` creates a candidate map only; browser render
  acknowledgement remains authoritative for visible completion.
- Native tool schemas reject undeclared top-level properties.

## Visibility Rule

The agent must not depend on embeddings, semantic retrieval, or vector ranking to decide which manifest tools are visible. Agent tool exposure is catalog-based.
