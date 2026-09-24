"""Deterministic validation of the model-owned capability route."""

from __future__ import annotations

import re

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentRunState,
    CapabilityRoute,
    CapabilityRouteDecision,
)
from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
_LOCATION_MAP_DISPLAY_TERMS = frozenset(
    {
        "show",
        "display",
        "view",
        "locate",
        "map",
        "put",
        "place",
        "landmark",
        "go",
        "take",
        "move",
        "bring",
        "navigate",
        "look",
        "mostrami",
        "portami",
        "montre",
        "montrez",
        "mappa",
    }
)
_LOCATION_MAP_DATA_TERMS = frozenset(
    {
        "find",
        "search",
        "near",
        "nearby",
        "within",
        "around",
        "poi",
        "amenity",
        "amenities",
        "cafe",
        "cafes",
        "clinic",
        "clinics",
        "hospital",
        "hospitals",
        "museum",
        "museums",
        "monument",
        "monuments",
        "temple",
        "temples",
        "cathedral",
        "cathedrals",
        "church",
        "churches",
        "castle",
        "castles",
        "palace",
        "palaces",
        "pharmacy",
        "pharmacies",
        "attraction",
        "attractions",
        "station",
        "stations",
        "data",
        "points",
    }
)
_PLACE_SEARCH_DATA_TERMS = frozenset(
    {
        "amenity",
        "amenities",
        "cafe",
        "cafes",
        "clinic",
        "clinics",
        "hospital",
        "hospitals",
        "museum",
        "museums",
        "pharmacy",
        "pharmacies",
        "poi",
        "station",
        "stations",
    }
)


###############################################################################
def build_location_map_fallback_route(user_message: str) -> CapabilityRoute | None:
    """Build a bounded map route when route bootstrap misses a plain place request."""

    terms = set(re.findall(r"[a-z0-9]+", user_message.casefold()))
    if not terms.intersection(_LOCATION_MAP_DISPLAY_TERMS):
        return None
    if terms.intersection(_LOCATION_MAP_DATA_TERMS):
        return None
    return CapabilityRoute(
        primary_domain=CapabilityDomain.PLACE_SEARCH,
        secondary_domains=[CapabilityDomain.MAP_RENDERING],
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["place search", "map viewport"],
        operation="show_location_on_map",
    )


###############################################################################
class CapabilityRouter:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry

    # -------------------------------------------------------------------------
    def validate_route(
        self,
        proposed: CapabilityRoute,
        *,
        user_message: str,
        active_state: AgentRunState,
    ) -> CapabilityRouteDecision:
        """Validate route semantics and return only an eligible shortlist."""

        reasons: list[str] = []
        rejected: list[str] = []
        valid_explicit_ids: list[str] = []
        proposed, semantic_reason = _normalize_route_semantics(proposed)
        if semantic_reason is not None:
            reasons.append(semantic_reason)
        proposed, discovery_reason = _normalize_capability_inventory_route(
            proposed, user_message=user_message
        )
        if discovery_reason is not None:
            reasons.append(discovery_reason)
        proposed, map_data_reason = _normalize_data_bearing_map_route(
            proposed, user_message=user_message
        )
        if map_data_reason is not None:
            reasons.append(map_data_reason)
        proposed, temporal_reason = _normalize_recent_scope(proposed)
        if temporal_reason is not None:
            reasons.append(temporal_reason)
        proposed, location_map_reason = _normalize_location_map_route(
            proposed, user_message=user_message
        )
        if location_map_reason is not None:
            reasons.append(location_map_reason)
        contract_reasons = _route_contract_reason_codes(proposed)
        if contract_reasons:
            return CapabilityRouteDecision(
                status="rejected",
                route=proposed,
                rejected_capability_ids=[],
                reason_codes=list(dict.fromkeys([*reasons, *contract_reasons])),
            )
        active_map_update = _is_active_map_update(proposed, active_state)
        if active_map_update and proposed.requires_location:
            proposed = proposed.model_copy(update={"requires_location": False})
            reasons.append("active_map_update_uses_current_map")
        for capability_id in proposed.explicit_capability_ids:
            normalized_id = capability_id.strip()
            capability = self.capability_registry.get_capability(normalized_id)
            if capability is None:
                rejected.append(normalized_id)
                reasons.append("unknown_capability_id")
                continue
            if not self.runtime_registry.is_enabled(normalized_id):
                rejected.append(normalized_id)
                reasons.append("capability_disabled")
                continue
            if not self.runtime_registry.access_available(normalized_id):
                rejected.append(normalized_id)
                reasons.append("capability_unavailable")
                continue
            valid_explicit_ids.append(normalized_id)

        if proposed.task_mode == "execute" and (
            _is_broad_infrastructure_route(proposed)
            or _is_ambiguous_infrastructure_message(user_message)
        ):
            return CapabilityRouteDecision(
                status="clarification",
                route=proposed,
                rejected_capability_ids=rejected,
                reason_codes=[
                    *dict.fromkeys([*reasons, "ambiguous_infrastructure_category"])
                ],
                clarification_question=(
                    "Which infrastructure category do you need: EV charging stations, "
                    "buildings, airports, roads/transit, or another specific category?"
                ),
            )

        # A new map cannot be prepared without a validated location.  Keep this
        # prerequisite server-owned so a model route that asks for a map but
        # forgets it still enters the typed location tool phase.
        if (
            proposed.task_mode == "execute"
            and proposed.presentation in {"map", "both"}
            and active_state.active_map_session is None
            and not proposed.requires_location
        ):
            proposed = proposed.model_copy(update={"requires_location": True})
            reasons.append("location_required_for_new_map")
        if (
            proposed.task_mode == "execute"
            and (proposed.target_refs or proposed.spatial_scope is not None)
            and not proposed.requires_location
            and not active_map_update
        ):
            proposed = proposed.model_copy(update={"requires_location": True})
            reasons.append("location_required_for_semantic_scope")

        route_domains = {proposed.primary_domain, *proposed.secondary_domains}
        if proposed.primary_domain is CapabilityDomain.MAP_STATE:
            if active_state.active_map_session is None:
                return CapabilityRouteDecision(
                    status="clarification",
                    route=proposed,
                    rejected_capability_ids=rejected,
                    reason_codes=[*dict.fromkeys([*reasons, "active_map_required"])],
                    clarification_question=(
                        "Which active map should I update, or would you like me to "
                        "prepare a new map first?"
                    ),
                )

        if proposed.task_mode == "clarify":
            if not proposed.clarification_question:
                return CapabilityRouteDecision(
                    status="rejected",
                    route=proposed,
                    rejected_capability_ids=rejected,
                    reason_codes=[*dict.fromkeys([*reasons, "clarification_question_missing"])],
                )
            return CapabilityRouteDecision(
                status="clarification",
                route=proposed,
                rejected_capability_ids=rejected,
                reason_codes=[*dict.fromkeys([*reasons, "model_requested_clarification"])],
                clarification_question=proposed.clarification_question,
            )

        if proposed.clarification_question is not None:
            reasons.append("clarification_question_not_allowed")

        catalog_discovery = proposed.operation == "discover_available_map_data"
        candidates = (
            []
            if catalog_discovery
            or (proposed.explicit_capability_ids and not valid_explicit_ids)
            else self.capability_registry.shortlist(
                domains=route_domains,
                queries=proposed.capability_queries,
                explicit_ids=valid_explicit_ids,
                runtime_registry=self.runtime_registry,
                limit=12,
                operation=proposed.operation,
                scope_kind=_concrete_scope_kind(proposed, active_state),
                temporal_mode=(
                    proposed.temporal_scope.mode
                    if proposed.temporal_scope.mode != "none"
                    else None
                ),
                temporal_granularity=proposed.temporal_scope.granularity,
                has_explicit_time_range=any(
                    value is not None
                    for value in (
                        proposed.temporal_scope.reference_time_iso,
                        proposed.temporal_scope.start_time_iso,
                        proposed.temporal_scope.end_time_iso,
                    )
                ),
                requires_render=proposed.presentation in {"map", "both"},
                location=_single_known_location(active_state),
            )
        )
        capability_ids = [
            str(item.get("id") or "").strip()
            for item in candidates
            if (
                str(item.get("id") or "").strip()
                and _is_executable_candidate(item)
                and str(item.get("id") or "").strip()
                not in active_state.excluded_capability_ids
            )
        ]

        if (
            proposed.task_mode == "execute"
            and not capability_ids
            and _is_unsupported_boundary_route(proposed)
        ):
            reason_codes = [*reasons, "unsupported_boundary_scope"]
            if active_state.active_map_session is not None:
                reason_codes.append("active_map_preserved")
            return CapabilityRouteDecision(
                status="clarification",
                route=proposed,
                rejected_capability_ids=rejected,
                reason_codes=list(dict.fromkeys(reason_codes)),
                clarification_question=(
                    "The enabled catalog does not provide an exact administrative "
                    "boundary layer for this request, so I left the active map "
                    "unchanged. Would a generalized geographic-context boundary "
                    "or another supported regional layer work instead?"
                ),
            )

        if proposed.task_mode == "execute" and not capability_ids:
            status = (
                "discovery_required"
                if not proposed.explicit_capability_ids
                else "no_capability"
            )
            no_candidate_reason = (
                [
                    "discovery_required"
                    if status == "discovery_required"
                    else "no_eligible_capability",
                    "no_renderable_capability",
                ]
                if proposed.presentation in {"map", "both"}
                else [
                    "discovery_required"
                    if status == "discovery_required"
                    else "no_eligible_capability"
                ]
            )
            return CapabilityRouteDecision(
                status=status,  # type: ignore[arg-type]
                route=proposed,
                rejected_capability_ids=rejected,
                reason_codes=[
                    *dict.fromkeys(
                        [
                            *reasons,
                            *no_candidate_reason,
                        ]
                    )
                ],
            )

        status = "rejected" if reasons and "clarification_question_not_allowed" in reasons else "accepted"
        return CapabilityRouteDecision(
            status=status,
            route=proposed,
            capability_ids=capability_ids,
            rejected_capability_ids=rejected,
            reason_codes=list(dict.fromkeys(reasons)),
        )

###############################################################################
def _is_executable_candidate(capability: dict[str, object]) -> bool:
    """Keep renderer-only descriptors out of the generic provider tool."""

    kind = str(
        capability.get("capabilityKind")
        or capability.get("capability_kind")
        or ""
    ).strip().casefold()
    return (
        kind != "basemap"
        and capability.get("runtime_render_ready") is not False
    )


###############################################################################
def _route_contract_reason_codes(route: CapabilityRoute) -> list[str]:
    """Enforce the route contract before any capability discovery or execution."""

    if route.task_mode not in {"answer", "clarify"}:
        return []
    reasons: list[str] = []
    if route.primary_domain is not CapabilityDomain.CONVERSATION:
        reasons.append("route_task_mode_requires_conversation_domain")
    if route.secondary_domains:
        reasons.append("route_task_mode_disallows_secondary_domains")
    if route.requires_location:
        reasons.append("route_task_mode_disallows_location_requirement")
    if route.presentation != "text":
        reasons.append("route_task_mode_disallows_map_presentation")
    if route.capability_queries:
        reasons.append("route_task_mode_disallows_capability_queries")
    if route.explicit_capability_ids:
        reasons.append("route_task_mode_disallows_capability_ids")
    if route.operation:
        reasons.append("route_task_mode_disallows_operation")
    if route.target_refs:
        reasons.append("route_task_mode_disallows_target_refs")
    if route.spatial_scope is not None:
        reasons.append("route_task_mode_disallows_spatial_scope")
    if route.filters:
        reasons.append("route_task_mode_disallows_filters")
    if route.temporal_scope.mode != "none" or any(
        value is not None
        for value in (
            route.temporal_scope.reference_time_iso,
            route.temporal_scope.start_time_iso,
            route.temporal_scope.end_time_iso,
        )
    ):
        reasons.append("route_task_mode_disallows_temporal_scope")
    if route.clarification_question is not None and route.task_mode == "answer":
        reasons.append("answer_route_disallows_clarification_question")
    return reasons


###############################################################################
def _single_known_location(state: AgentRunState) -> ResolvedLocation | None:
    if len(state.location_refs) == 1:
        return next(iter(state.location_refs.values()))
    if state.active_map_session is not None:
        return state.active_map_session.resolved_location
    return None


_ACTIVE_MAP_UPDATE_OPERATIONS = frozenset(
    {
        "remove_layer",
        "set_layer_visibility",
        "set_layer_opacity",
        "set_basemap",
        "keep_only_layers",
        "fit_layer",
        "reset_view",
    }
)


###############################################################################
def _is_active_map_update(route: CapabilityRoute, state: AgentRunState) -> bool:
    """Return whether the route mutates the already-rendered map session."""

    return (
        route.task_mode == "execute"
        and route.primary_domain is CapabilityDomain.MAP_STATE
        and state.active_map_session is not None
        and str(route.operation or "").strip().casefold()
        in _ACTIVE_MAP_UPDATE_OPERATIONS
        and route.spatial_scope is None
    )

###############################################################################
def _route_terms(route: CapabilityRoute) -> set[str]:
    values = [route.operation or "", *route.capability_queries]
    return {
        token
        for value in values
        for token in re.findall(r"[a-z0-9]+", str(value).casefold())
        if len(token) > 1
    }


###############################################################################
def _is_broad_infrastructure_route(route: CapabilityRoute) -> bool:
    terms = _route_terms(route)
    if "infrastructure" not in terms:
        return False
    specific_terms = terms.difference(
        {
            "and",
            "category",
            "categories",
            "data",
            "find",
            "get",
            "general",
            "infrastructure",
            "kind",
            "kinds",
            "layer",
            "map",
            "nearby",
            "of",
            "on",
            "retrieve",
            "show",
            "specific",
            "subtype",
            "subtypes",
            "the",
            "to",
            "type",
            "types",
        }
    )
    return not specific_terms


###############################################################################
def _is_ambiguous_infrastructure_message(user_message: str) -> bool:
    """Guard raw generic infrastructure wording before model subtype guesses."""

    terms = set(re.findall(r"[a-z0-9]+", user_message.casefold()))
    if "infrastructure" not in terms:
        return False
    subtype_terms = {
        "airport",
        "airports",
        "building",
        "buildings",
        "charging",
        "charger",
        "chargers",
        "ev",
        "electric",
        "electricity",
        "power",
        "road",
        "roads",
        "transit",
        "transport",
        "utility",
        "utilities",
    }
    return not terms.intersection(subtype_terms)


###############################################################################
def _is_unsupported_boundary_route(route: CapabilityRoute) -> bool:
    if route.spatial_scope is None:
        return False
    if route.spatial_scope.kind != "administrative_geometry":
        return False
    terms = _route_terms(route)
    return bool(
        terms.intersection(
            {
                "boundary",
                "boundaries",
                "exact",
                "precise",
                "precision",
                "administrative",
            }
        )
    )

###############################################################################
def _normalize_route_semantics(
    route: CapabilityRoute,
) -> tuple[CapabilityRoute, str | None]:
    """Canonicalize model spelling before registry operation/query matching."""

    raw_operation = route.operation
    operation = None
    if raw_operation is not None:
        operation = re.sub(
            r"[^a-z0-9]+", "_", str(raw_operation).casefold()
        ).strip("_")
    normalized_queries = [
        re.sub(
            r"\s+",
            " ",
            re.sub(r"[^a-z0-9]+", " ", str(query).casefold()),
        ).strip()
        for query in route.capability_queries
        if str(query).strip()
    ]
    changed = operation != raw_operation or normalized_queries != list(
        route.capability_queries
    )
    if not changed:
        return route, None
    return (
        route.model_copy(
            update={
                "operation": operation,
                "capability_queries": normalized_queries,
            }
        ),
        "route_semantics_normalized",
    )


###############################################################################
def _normalize_capability_inventory_route(
    route: CapabilityRoute,
    *,
    user_message: str,
) -> tuple[CapabilityRoute, str | None]:
    """Turn broad catalog questions into discovery-only routes."""

    if (
        route.primary_domain is not CapabilityDomain.PROVIDER_DISCOVERY
        or route.task_mode != "execute"
        or route.presentation != "text"
    ):
        return route, None

    message_terms = set(re.findall(r"[a-z0-9]+", user_message.casefold()))
    asks_inventory = bool(
        message_terms.intersection({"what", "which", "list", "available"})
        and message_terms.intersection(
            {
                "data",
                "dataset",
                "datasets",
                "layer",
                "layers",
                "capability",
                "capabilities",
                "basemap",
                "basemaps",
            }
        )
    ) or (
        "show" in message_terms
        and message_terms.intersection(
            {
                "data",
                "dataset",
                "datasets",
                "layer",
                "layers",
                "capability",
                "capabilities",
                "basemap",
                "basemaps",
            }
        )
    )
    if not asks_inventory:
        return route, None

    generic_terms = {
        "a",
        "an",
        "and",
        "available",
        "basemap",
        "basemaps",
        "can",
        "capabilities",
        "capability",
        "data",
        "dataset",
        "datasets",
        "do",
        "display",
        "for",
        "geospatial",
        "in",
        "layer",
        "layers",
        "list",
        "map",
        "maps",
        "me",
        "load",
        "not",
        "of",
        "on",
        "or",
        "show",
        "supported",
        "the",
        "to",
        "what",
        "which",
        "you",
    }
    target_terms = {
        term
        for target in [
            *route.target_refs,
            *(
                route.spatial_scope.target_refs
                if route.spatial_scope is not None
                else []
            ),
        ]
        for term in re.findall(r"[a-z0-9]+", target.casefold())
    }
    has_specific_subject = bool(message_terms - generic_terms - target_terms)
    operation = "discover_available_map_data"
    query_update = {} if has_specific_subject else {"capability_queries": []}
    if route.operation == operation and not query_update:
        return route, None
    return (
        route.model_copy(update={"operation": operation, **query_update}),
        "capability_inventory_route_normalized",
    )


###############################################################################
def _normalize_data_bearing_map_route(
    route: CapabilityRoute,
    *,
    user_message: str = "",
) -> tuple[CapabilityRoute, str | None]:
    """Keep data-bearing map requests on a route eligible for data tools."""

    operation = str(route.operation or "").strip().casefold()
    if route.task_mode != "execute" or route.presentation not in {"map", "both"}:
        return route, None

    if route.primary_domain is CapabilityDomain.PLACE_SEARCH:
        message_terms = set(re.findall(r"[a-z0-9]+", user_message.casefold()))
        query_terms = {
            term
            for query in route.capability_queries
            for term in re.findall(r"[a-z0-9]+", query.casefold())
        }
        data_query = bool(
            message_terms.intersection(_PLACE_SEARCH_DATA_TERMS)
            or query_terms.intersection(_PLACE_SEARCH_DATA_TERMS)
            or any(
                query.strip().casefold()
                in {"overpass_poi_amenities", "points of interest"}
                for query in route.capability_queries
            )
        )
        if data_query:
            secondary_domains = [
                CapabilityDomain.MAP_RENDERING,
                CapabilityDomain.DATA_RETRIEVAL,
                *(
                    domain
                    for domain in route.secondary_domains
                    if domain
                    not in {
                        CapabilityDomain.MAP_RENDERING,
                        CapabilityDomain.DATA_RETRIEVAL,
                    }
                ),
            ]
            return (
                route.model_copy(
                    update={"secondary_domains": secondary_domains[:3]}
                ),
                "data_bearing_place_search_route_normalized",
            )

    if (
        route.primary_domain
        not in {CapabilityDomain.MAP_STATE, CapabilityDomain.MAP_RENDERING}
        or operation != "add_layer"
        or not (route.capability_queries or route.explicit_capability_ids)
    ):
        return route, None
    secondary_domains = list(route.secondary_domains)
    if CapabilityDomain.DATA_RETRIEVAL not in secondary_domains:
        secondary_domains.append(CapabilityDomain.DATA_RETRIEVAL)
    return (
        route.model_copy(
            update={
                "primary_domain": CapabilityDomain.MAP_RENDERING,
                "secondary_domains": secondary_domains[:3],
            }
        ),
        "data_bearing_map_route_normalized",
    )

###############################################################################
def _normalize_recent_scope(
    route: CapabilityRoute,
) -> tuple[CapabilityRoute, str | None]:
    """Treat undated recent-feed intent as current, not historical."""

    temporal = route.temporal_scope
    granularity = temporal.granularity.strip().casefold()
    has_explicit_time = any(
        value is not None
        for value in (
            temporal.reference_time_iso,
            temporal.start_time_iso,
            temporal.end_time_iso,
        )
    )
    if (
        temporal.mode == "historical"
        and not has_explicit_time
        and granularity in {"current", "latest", "live", "near_real_time", "recent"}
    ):
        return (
            route.model_copy(
                update={
                    "temporal_scope": temporal.model_copy(update={"mode": "current"})
                }
            ),
            "recent_scope_normalized_to_current",
        )
    return route, None

###############################################################################
def _normalize_location_map_route(
    route: CapabilityRoute,
    *,
    user_message: str = "",
) -> tuple[CapabilityRoute, str | None]:
    """Keep location-only map requests on the map-planning route.

    A model can describe a request to display a resolved place as a geocoding
    operation.  That route is a data route and therefore filters out the
    metadata-only location resolver when a render is required, leaving no
    eligible capability and no path to ``apply_map_plan``.  Normalize only the
    bounded location-only vocabulary; data-bearing place-search requests keep
    their original route.
    """

    if (
        route.task_mode != "execute"
        or route.presentation not in {"map", "both"}
        or route.primary_domain is not CapabilityDomain.PLACE_SEARCH
        or any(
            domain is not CapabilityDomain.MAP_RENDERING
            for domain in route.secondary_domains
        )
    ):
        return route, None
    operation = str(route.operation or "").strip().casefold()
    message_terms = set(re.findall(r"[a-z0-9]+", user_message.casefold()))
    display_terms = _LOCATION_MAP_DISPLAY_TERMS
    data_terms = _LOCATION_MAP_DATA_TERMS
    raw_landmark_display = (
        route.primary_domain is CapabilityDomain.PLACE_SEARCH
        and route.presentation in {"map", "both"}
        and bool(message_terms.intersection(display_terms))
        and not bool(message_terms.intersection(data_terms))
    )
    location_operations = {
        "geocode",
        "locate",
        "resolve_location",
        "resolve_place",
    }
    route_data_queries = {
        "amenities",
        "amenity search",
        "overpass_poi_amenities",
        "poi",
        "points of interest",
    }
    location_queries = {
        str(query).strip().casefold()
        for query in route.capability_queries
        if str(query).strip()
    }
    location_query_vocabulary = {
        "coordinates",
        "geocoding",
        "landmark lookup",
        "location lookup",
        "map viewport",
        "map view of a named feature",
        "place search",
        "reverse geocoding",
    }
    if not (
        raw_landmark_display
        or (
            operation in location_operations
            and not bool(location_queries.intersection(route_data_queries))
            and not bool(message_terms.intersection(data_terms))
        )
        or (
            location_queries
            and location_queries <= location_query_vocabulary
            and "place search" in location_queries
        )
    ):
        return route, None
    return (
        route.model_copy(
            update={
                "primary_domain": CapabilityDomain.MAP_RENDERING,
                "capability_queries": ["place search", "map viewport"],
                "operation": "show_location_on_map",
            }
        ),
        "location_map_route_normalized",
    )


###############################################################################
def _concrete_scope_kind(
    route: CapabilityRoute, active_state: AgentRunState
) -> str | None:
    """Return a concrete provider scope only after location resolution."""

    scope = route.spatial_scope
    if scope is None:
        return None
    if scope.kind in {"administrative_geometry", "feature_geometry"}:
        location = _single_known_location(active_state)
        return "bbox" if location is not None and location.bbox else None
    if scope.kind == "radius":
        # Radius is a user-facing semantic scope. Provider contracts receive
        # the bounded bbox produced from it after location binding.
        return "bbox" if _single_known_location(active_state) is not None else None
    return scope.kind
