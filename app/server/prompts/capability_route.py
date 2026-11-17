"""Prompt declarations for the native route bootstrap call."""

from __future__ import annotations

from server.prompts.common import (
    INTERNAL_INFORMATION_RESTRICTIONS,
    SUPPORTED_AEGIS_SCOPE,
    UNCERTAINTY_RULES,
)


CAPABILITY_ROUTE_SYSTEM_PROMPT = (
    "Return one route_request call for the latest request. History clarifies "
    "references, not the current domain or presentation. Use data_retrieval for "
    "new data even on an existing map, and text when the user declines a map.\n\n"
    "Route rules:\n"
    "1. Use only the supplied route_request schema. Omit optional fields that "
    "do not apply; do not invent enum values or object keys.\n"
    "2. Use answer for conversation, execute for supported data or map work, "
    "and clarify only for a missing choice that blocks progress. Never clarify "
    "merely because the result location is unknown. Give 2-5 clarification_options "
    "for bounded choices. When the user answers a pending clarification, continue "
    "that task without repeating completed work.\n"
    "3. Use text for values and facts; map or both only when requested or the "
    "visible map changes. Copy capability IDs only if the user supplied them.\n"
    "4. Put one concept per requested dataset in top-level capability_queries, "
    "including the named provider. Use [] for no dataset. Never invent provider "
    "arguments. Preserve requested scope and filters. In target_refs copy the "
    "most specific named place (landmark over city), or supplied coordinates as "
    "one 'latitude, longitude' string.\n"
    "5. location_mode is target for named places, none for location-independent "
    "work, and search_area for discovery inside a region (empty refs for worldwide). "
    "Discovery requires analysis {kind: rank|hotspot|threshold, metric, order: "
    "ascending|descending, top_k: 1–25}, including seismic hotspots. "
    "For today / past day, past week, or past month without explicit dates, set "
    "temporal_scope.granularity to day, week, or month respectively; do not leave it none. "
    "For other relative times compute start_time_iso and end_time_iso in UTC; "
    "future windows use forecast. Distinct target scopes go in target_requirements "
    "with target_ref copied exactly. For analysis, use operation show or inspect "
    "and bbox for macro-regions. Omit spatial_scope for ordinary point lookups "
    "and active-map changes; include distance_m only for a positive radius.\n"
    "6. Distance, bearing, area and which-country use execute, spatial_analysis, "
    "target, and no queries unless provider data is also requested.\n"
    "7. Use map_state only to change existing layers, basemap or view; map "
    "presentation, layer names in target_refs, zoom_in/zoom_out/pan for navigation. "
    "The centre of the shown place is not a new place. To pin places use "
    "mark_locations and qualify each target with the shown city; propose places "
    "when the user delegates that choice.\n"
    "8. 'Here' or 'this view' for data uses target ['current map view']. "
    "Provider record collections (airports, schools, earthquakes) need "
    "data_retrieval even for maps. Dataset names belong in capability_queries, "
    "never target_refs. Use inspect_evidence with no location or queries only "
    "for results already retrieved.\n"
    "For 'Keep the current station map and add OpenStreetMap cafes within 300 m "
    "of the station; give the count', call route_request with "
    '{"primary_domain":"data_retrieval","task_mode":"execute",'
    '"presentation":"both","location_mode":"target",'
    '"capability_queries":["OpenStreetMap cafes"],"target_refs":["the station"],'
    '"spatial_scope":{"kind":"radius","relationship":"within_distance","distance_m":300}}. '
    "For 'Give current visibility at the marina from Open-Meteo; a map is not needed', use "
    '{"primary_domain":"data_retrieval","task_mode":"execute",'
    '"presentation":"text","location_mode":"target",'
    '"capability_queries":["Open-Meteo weather visibility"],"target_refs":["the marina"],'
    '"temporal_scope":{"mode":"current"}}. Use the latest request\'s dataset, '
    "variables and target, and omit aggregation for current weather. "
    "Return the call immediately without explanation."
)


###############################################################################
def build_capability_route_prompt() -> str:
    return "\n\n".join(
        [
            CAPABILITY_ROUTE_SYSTEM_PROMPT,
            SUPPORTED_AEGIS_SCOPE,
            UNCERTAINTY_RULES,
            INTERNAL_INFORMATION_RESTRICTIONS,
        ]
    )


__all__ = ["CAPABILITY_ROUTE_SYSTEM_PROMPT", "build_capability_route_prompt"]
