from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

from typing import Any, cast

from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.interpretation import CanonicalRequestInterpretation
from server.contracts.extraction import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry

###############################################################################
class ToolArgumentBuilder:

    # -------------------------------------------------------------------------
    def __init__(self, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry

    # -------------------------------------------------------------------------
    def build_location_arguments(
        self,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
        resolved_location: ResolvedLocation | None = None,
        canonical_request: CanonicalRequestInterpretation | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        if canonical_request is not None:
            target = (
                canonical_request.target(target_id)
                if target_id
                else canonical_request.primary_target
            )
            # Once the canonical contract exists it is the only location
            # authority.  Falling through to parser text, memory, or a
            # viewport would allow a provider adapter to geocode a different
            # place after interpretation has already completed.
            if target is None or target.resolved_location is None:
                return {}
            location = target.resolved_location
            return {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "location": location.label,
            }
        if resolved_location is not None:
            arguments: dict[str, Any] = {
                "latitude": resolved_location.latitude,
                "longitude": resolved_location.longitude,
                "location": resolved_location.label,
            }
            return arguments
        for signal in sorted(
            turn.location_signals,
            key=self._location_signal_priority,
            reverse=True,
        ):
            if signal.signal_type == "deictic":
                continue
            if signal.latitude is not None and signal.longitude is not None:
                return {
                    "latitude": signal.latitude,
                    "longitude": signal.longitude,
                    "location": signal.normalized_value or signal.raw_value,
                }
            if signal.normalized_value or signal.raw_value:
                return {"location": signal.normalized_value or signal.raw_value}
        active = (memory_snapshot or {}).get("active_location")
        if is_json_object(active):
            latitude = active.get("latitude")
            longitude = active.get("longitude")
            if isinstance(latitude, int | float) and isinstance(longitude, int | float):
                return {
                    "latitude": latitude,
                    "longitude": longitude,
                    "location": active.get("label"),
                }
        if turn.map_target:
            return {"location": turn.map_target}
        return {"query": turn.user_text}

    # -------------------------------------------------------------------------
    def build_bbox_arguments(
        self,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
        resolved_location: ResolvedLocation | None = None,
        canonical_request: CanonicalRequestInterpretation | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        if canonical_request is not None:
            target = (
                canonical_request.target(target_id)
                if target_id
                else canonical_request.primary_target
            )
            constraint = (
                next(
                    (
                        item
                        for item in canonical_request.spatial_constraints
                        if item.target_id == target.target_id
                    ),
                    None,
                )
                if target is not None
                else (
                    canonical_request.spatial_constraints[0]
                    if canonical_request.spatial_constraints
                    else None
                )
            )
            if constraint is not None and constraint.analysis_scope == "radius":
                if target is None or target.resolved_location is None:
                    return {}
                location = target.resolved_location
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "radius_m": constraint.distance_m,
                }
            if constraint is not None and constraint.analysis_scope == "point":
                if target is None or target.resolved_location is None:
                    return {}
                location = target.resolved_location
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "location": location.label,
                }
            if constraint is not None and constraint.analysis_scope in {
                "viewport",
                "administrative_geometry",
                "feature_geometry",
            }:
                # A display viewport is not an analysis area, and a geocoder
                # bbox is only a prefilter.  Without an explicit geometry or
                # committed viewport reference, fail closed instead of
                # silently turning either request into a bbox query.
                return {}
            if target is None or target.resolved_location is None:
                return {}
            location = target.resolved_location
            if location.bbox is not None:
                return {"bbox": list(location.bbox)}
            return {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "location": location.label,
            }
        if resolved_location is not None and resolved_location.bbox is not None:
            return {"bbox": list(resolved_location.bbox)}
        if self._has_explicit_location_signal(turn):
            return self.build_location_arguments(
                turn, memory_snapshot, resolved_location=resolved_location
            )
        memory = memory_snapshot or {}
        for candidate in (
            memory.get("bbox"),
            json_object(memory.get("viewport")).get("bbox"),
            json_object(memory.get("active_visualization")).get("bounds"),
        ):
            if (
                is_json_array(candidate)
                and len(candidate) == 4
                and all(isinstance(value, int | float) for value in candidate)
            ):
                return {"bbox": candidate}
        return self.build_location_arguments(
                turn, memory_snapshot, resolved_location=resolved_location
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _location_signal_priority(signal: Any) -> tuple[int, float]:
        priorities = {
            "coordinates": 6,
            "address": 5,
            "poi": 5,
            "street": 5,
            "neighborhood": 4,
            "district": 4,
            "municipality": 3,
            "city": 3,
            "county": 2,
            "province": 2,
            "state": 2,
            "region": 2,
            "country": 1,
            "deictic": 0,
        }
        return (
            priorities.get(getattr(signal, "signal_type", ""), 0),
            float(getattr(signal, "confidence", 0.0) or 0.0),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_explicit_location_signal(turn: TurnParseResult) -> bool:
        for signal in turn.location_signals:
            if signal.signal_type == "deictic":
                continue
            if str(signal.raw_value or "").strip():
                return True
        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def build_temporal_arguments(
        turn: TurnParseResult,
        canonical_request: CanonicalRequestInterpretation | None = None,
    ) -> dict[str, Any]:
        temporal = (
            canonical_request.temporal_constraints
            if canonical_request is not None
            else turn.temporal_signal
        )
        if temporal.mode == "none":
            return {}
        arguments: dict[str, Any] = {"temporal_mode": temporal.mode}
        # Current-mode requests do not need a free-form time argument.  The
        # parser can occasionally place the remainder of a compound request
        # in raw_text (for example, "show the weather there"); forwarding
        # that text to a provider makes the tool call look temporal even
        # though no temporal constraint was requested.  Forecast and
        # historical handlers use the phrase to select the requested slice.
        if (
            canonical_request is None
            and temporal.mode in {"forecast", "historical"}
            and temporal.raw_text
            and not (temporal.start_time_iso or temporal.end_time_iso)
        ):
            # A provider may still need a short selection token when the
            # parser could not resolve a relative phrase (for example,
            # ``tomorrow``). Once canonical boundaries exist, ISO values are
            # authoritative and forwarding the original prose would allow an
            # adapter to reinterpret the request a second time.
            arguments["time"] = temporal.raw_text
        if temporal.reference_time_iso:
            arguments["reference_time_iso"] = temporal.reference_time_iso
        if temporal.start_time_iso:
            arguments["start_time_iso"] = temporal.start_time_iso
        if temporal.end_time_iso:
            arguments["end_time_iso"] = temporal.end_time_iso
        if temporal.granularity != "none":
            arguments["temporal_granularity"] = temporal.granularity
        if temporal.aggregation != "none":
            arguments["aggregation"] = temporal.aggregation
        return arguments

    # -------------------------------------------------------------------------
    def build_capability_arguments(
        self,
        capability_id: str,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
        resolved_location: ResolvedLocation | None = None,
        canonical_request: CanonicalRequestInterpretation | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        capability = (
            self.capability_registry.get_capability(capability_id)
            if self.capability_registry is not None
            else {}
        ) or {}
        metadata = json_object(capability.get("metadata"))
        is_direct = (
            str(capability.get("type") or "").casefold() == "direct-tool"
            or str(metadata.get("retrieval_mode") or "").casefold() == "direct"
        )
        arguments = (
            self.build_location_arguments(
                turn,
                memory_snapshot,
                resolved_location=resolved_location,
                canonical_request=canonical_request,
                target_id=target_id,
            )
            if is_direct
            else self.build_bbox_arguments(
                turn,
                memory_snapshot,
                resolved_location=resolved_location,
                canonical_request=canonical_request,
                target_id=target_id,
            )
        )
        arguments.update(self.build_temporal_arguments(turn, canonical_request))
        canonical_filters = (
            canonical_request.filters if canonical_request is not None else {}
        )
        raw_categories = (
            canonical_filters.get("poi_categories")
            if canonical_request is not None
            else turn.poi_categories
        )
        category_items = (
            cast(list[Any], raw_categories)
            if isinstance(raw_categories, list)
            else []
        )
        categories = [
            str(item).strip()
            for item in category_items
            if str(item).strip()
        ]
        if categories:
            categories = list(dict.fromkeys(categories))
            arguments["poi_categories"] = categories
            arguments["categories"] = categories
        radius_m = (
            None
            if canonical_request is not None
            else turn.radius_m
        )
        if canonical_request is not None:
            radius_m = next(
                (
                    constraint.distance_m
                    for constraint in canonical_request.spatial_constraints
                    if constraint.analysis_scope == "radius"
                    and (target_id is None or constraint.target_id == target_id)
                ),
                None,
            )
        if (
            canonical_request is None
            and radius_m is None
            and turn.viewport_intent is not None
        ):
            radius_m = turn.viewport_intent.radius_hint_m
        if radius_m is not None:
            arguments["radius_m"] = radius_m
        canonical_limit = canonical_filters.get("limit")
        if canonical_request is not None:
            if isinstance(canonical_limit, int) and not isinstance(canonical_limit, bool):
                arguments["limit"] = canonical_limit
        elif turn.result_limit is not None:
            arguments["limit"] = turn.result_limit
        if capability and str(capability.get("type") or "").casefold() == "direct-tool":
            canonical_entity_target = canonical_filters.get("entity_target")
            if canonical_request is not None:
                if isinstance(canonical_entity_target, str) and canonical_entity_target.strip():
                    arguments["query"] = canonical_entity_target.strip()
                elif categories:
                    arguments["query"] = ", ".join(categories)
            elif turn.entity_target:
                arguments["query"] = turn.entity_target
            elif turn.poi_categories:
                arguments["query"] = ", ".join(turn.poi_categories)
        raw_attributes = (
            canonical_filters.get("attributes")
            if canonical_request is not None
            else turn.requested_attributes
        )
        if isinstance(raw_attributes, list) and raw_attributes:
            attribute_items = cast(list[Any], raw_attributes)
            arguments["requested_attributes"] = list(
                dict.fromkeys(
                    str(item).strip()
                    for item in attribute_items
                    if str(item).strip()
                )
            )
        return {key: value for key, value in arguments.items() if value is not None}
