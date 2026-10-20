# Agent Catalog Contract

Last updated: 2026-10-20

## Stable native boundary

The native runtime keeps one fixed, typed tool registry. The model receives a
state-dependent subset of that registry; registration does not mean that a
tool is exposed on every model turn.

The model-visible names are:

- `route_request` (internal route bootstrap)
- `resolve_geospatial_location`
- `discover_geospatial_capabilities`
- `discover_geospatial_provider_layers` (provider-discovery routes only)
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `inspect_evidence`
- `transform_evidence`
- `apply_map_plan`
- `search_conversation_history` (conditional history-repository registration)

The evidence transformation tool is `transform_evidence`.

`discover_geospatial_capabilities` is the single generic model-facing
capability-discovery responsibility. `discover_geospatial_provider_layers` is
also model-facing, but only on an explicit provider-discovery route (its
`provider_discovery_route` prerequisite); it is not an interchangeable
discovery alternative. A request to add a named provider's layer to the map
("add the RainViewer radar") is normalized to a data-bearing map route, so it
uses `execute_geospatial_capability` rather than provider-layer listing.

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

## Search areas and evidence analytics

`location_mode` replaces the old boolean route prerequisite without a legacy
alias. `search_area` uses explicit area references and defaults to World;
`analysis` contains kind (`rank`, `hotspot`, `threshold`), metric, order and top_k
(1–25). Each capability query describes one distinct retrieval objective.
The macro-region reference catalog is static, cached and alias-only, with
validated bboxes, unique aliases and member-country lists used for land and
region masks; it is not database seeded.

`executionContract.preferred_bbox` ([west, south, east, north]) ranks a
regional source above global equivalents only when the resolved location falls
inside it (and below them outside it); `emsc_earthquakes` uses it for the
Euro-Mediterranean area.

`grid_sample` declares support for server-owned area sampling. Open-Meteo
weather supports a capped grid; other manifests retain their existing point or
bbox contracts. Provider coverage must disclose point-centre substitutions.

`transform_evidence` supports numeric sort, ISO/epoch temporal filtering,
lat/lon spatial filtering, sum/count/mean/max/min aggregation, and grid bins
with count, sum, mean, max, representative, centre and cell bounds. Derived
payloads use `features`; summaries carry bbox, located count and value fields.
Provenance chains retain provider, coverage, units, observation time and value
kind. `add_evidence_layer.value_encoding` accepts graduated or heatmap plus a
numeric field. The server computes the range and rejects invalid fields with
correctable `invalid_value_field`.
