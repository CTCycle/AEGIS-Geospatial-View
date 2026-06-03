# Agent Catalog Contract

Last updated: 2026-06-02

## Stable Native Tools

The agent accesses manifests through three stable native tools:

- `list_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`

## Tool Rules

- `list_geospatial_capabilities` returns compact metadata only.
- Pagination must be deterministic.
- Page size is capped at 50.
- `describe_geospatial_capability` returns one full manifest descriptor plus executable argument schema.
- `execute_geospatial_capability` validates supplied arguments against the manifest schema before execution.

## Visibility Rule

The agent must not depend on embeddings, semantic retrieval, or vector ranking to decide which manifest tools are visible. Agent tool exposure is catalog-based.
