# Agent Catalog Contract

Last updated: 2026-09-19

## Stable native boundary

The native runtime keeps one fixed, typed tool registry. The model receives a
state-dependent subset of that registry; registration does not mean that a
tool is exposed on every model turn.

The model-visible names are:

- `route_request` (internal route bootstrap)
- `resolve_geospatial_location`
- `discover_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `inspect_evidence`
- `transform_evidence`
- `apply_map_plan`
- `search_conversation_history` (conditional history-repository registration)

The evidence transformation tool is `transform_evidence`.

`discover_geospatial_capabilities` is the single generic model-facing
capability-discovery responsibility. The separately registered
`discover_geospatial_provider_layers` handler is internal and may enrich the
generic result for an explicit provider-discovery route; it is not presented as
an interchangeable discovery alternative.

## Progressive exposure

At each model decision, exposure is a projection of the currently unmet
route and completion responsibilities:

| Responsibility still pending | Tools that may be exposed |
|---|---|
| Route bootstrap | `route_request` only, internally |
| Plain answer, clarification, or finalization | No model-facing tools |
| Required location unresolved | `resolve_geospatial_location` |
| No validated capability shortlist | `discover_geospatial_capabilities` |
| Shortlist selected and detail needed | `describe_geospatial_capability` |
| Shortlist selected and data required | `execute_geospatial_capability` |
| Evidence analysis or transformation required | `inspect_evidence`, `transform_evidence` |
| Map presentation still pending | `apply_map_plan` |
| Earlier conversation must be recalled | `search_conversation_history` |

Location-dependent discovery follows location resolution. Evidence and history
are exposed only when the current responsibility requires them; the mere
presence of stored evidence or a conversation history does not make those
tools generally available. The sequence is not a fixed workflow: the
registry is filtered again after each state update and completion evaluation.

## Tool rules

- `discover_geospatial_capabilities` returns compact, deterministic catalog
  metadata only. Pagination is deterministic and page size is capped at 50.
- `describe_geospatial_capability` returns one full manifest descriptor plus
  its executable argument schema.
- `execute_geospatial_capability` validates supplied arguments against the
  manifest schema before execution; the server owns resolved geography and
  temporal binding.
- `discover_geospatial_provider_layers` accepts only policy-allowed provider
  IDs on its explicit provider-native route and returns normalized descriptors,
  never raw provider XML or credentials.
- `inspect_evidence` returns bounded views of stored evidence and never an
  unrestricted payload.
- `transform_evidence` accepts only bounded declarative vector/tabular
  operations and persists a derived evidence record with parent provenance.
- `apply_map_plan` creates a candidate map only; browser render
  acknowledgement remains authoritative for visible completion.
- Native tool schemas reject undeclared top-level properties.

## Visibility rule

Tool exposure is catalog-based and responsibility-driven. The registry must not
depend on embeddings, semantic retrieval, or vector ranking to decide which
manifest tools are visible. A tool is exposed only when its route phase and
state-owned prerequisites match the current unmet completion contract.
