"""Deterministically compile parser evidence into canonical request state."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from server.contracts.extraction import TurnParseResult
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.interpretation import (
    CanonicalPresentation,
    CanonicalRequestInterpretation,
    CanonicalSpatialConstraint,
    CanonicalTarget,
    CanonicalTemporalConstraints,
    CompletionRequirement,
    normalize_target_key,
)


FLOOD_COMPARISON_AMBIGUITY = "flood_comparison_requires_comparable_semantics"


class RequestInterpreter:
    """Compile once; downstream services must consume this value verbatim."""

    _COMPARISON_OPERATIONS = frozenset({"compare", "comparison"})
    _FLOOD_COMPARISON_DOMAIN_TERMS = (
        "flood",
        "gauge",
        "tide",
        "water level",
        "water levels",
        "waterlevel",
    )

    _SPECIFICITY = {
        "coordinates": 6,
        "address": 5,
        "airport": 5,
        "feature": 5,
        "landmark": 5,
        "poi": 5,
        "river": 5,
        "road": 5,
        "street": 5,
        "station": 5,
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

    def compile(
        self,
        *,
        request_id: str,
        turn: TurnParseResult,
        resolved_location: ResolvedLocation | None = None,
        resolved_locations: dict[str, ResolvedLocation] | None = None,
        memory_snapshot: dict[str, Any] | None = None,
        request_datetime: str | datetime | None = None,
        client_timezone: str | None = None,
        application_timezone: str = "UTC",
    ) -> CanonicalRequestInterpretation:
        signals = [
            item
            for item in turn.location_signals
            if item.signal_type != "deictic" and item.raw_value.strip()
        ]
        signals.sort(
            key=lambda item: self._SPECIFICITY.get(item.signal_type, 0), reverse=True
        )
        targets: list[CanonicalTarget] = []
        seen: set[str] = set()
        resolved_by_key = {
            self._key(str(key)): value
            for key, value in (resolved_locations or {}).items()
            if self._key(str(key))
        }
        for index, signal in enumerate(signals):
            key = self._key(signal.normalized_value or signal.raw_value)
            if not key or key in seen:
                continue
            seen.add(key)
            is_primary = index == 0
            signal_location = (
                resolved_by_key.get(key)
                or (resolved_location if is_primary else None)
            )
            targets.append(
                CanonicalTarget(
                    target_id=f"target-{len(targets) + 1}",
                    original_text=signal.raw_value,
                    entity_kind=signal.signal_type,
                    resolved_location=signal_location,
                    resolution_status=(
                        "resolved"
                        if signal_location is not None
                        else "unresolved"
                    ),
                    peer=not is_primary
                    and self._SPECIFICITY.get(signal.signal_type, 0)
                    >= self._SPECIFICITY.get(signals[0].signal_type, 0),
                )
            )

        if not targets and resolved_location is not None:
            targets.append(
                CanonicalTarget(
                    target_id="target-1",
                    original_text=resolved_location.label,
                    entity_kind=resolved_location.location_type or "location",
                    resolved_location=resolved_location,
                    resolution_status="inherited",
                )
            )

        primary = targets[0] if targets else None
        if primary is not None and len(targets) > 1:
            # Less-specific signals are parents of the most-specific entity;
            # same-level signals remain peers for comparison/combination work.
            primary.parent_target_ids = [
                item.target_id
                for item in targets[1:]
                if not item.peer
            ]

        relationship = turn.relationship
        spatial: list[CanonicalSpatialConstraint] = []
        relationship_evidence = list(turn.geographic_relationships)
        target_by_key = {
            self._key(target.original_text): target for target in targets
        }
        for evidence in relationship_evidence:
            target = target_by_key.get(self._key(evidence.target))
            if target is None:
                continue
            reference = target_by_key.get(self._key(evidence.reference or ""))
            if (
                reference is not None
                and evidence.relationship in {"in", "at"}
                and reference.target_id not in target.parent_target_ids
            ):
                target.parent_target_ids.append(reference.target_id)
            spatial.append(
                CanonicalSpatialConstraint(
                    relationship=evidence.relationship,
                    target_id=target.target_id,
                    reference_target_id=reference.target_id if reference else None,
                    analysis_scope=evidence.analysis_scope,
                    distance_m=evidence.distance_m,
                    provenance="explicit",
                )
            )
        if not spatial and primary is not None:
            scoped_targets = [primary, *[item for item in targets if item.peer]]
            for target in scoped_targets:
                if turn.radius_m is not None:
                    spatial.append(
                        CanonicalSpatialConstraint(
                            relationship="within_distance",
                            target_id=target.target_id,
                            analysis_scope="radius",
                            distance_m=turn.radius_m,
                            provenance="explicit",
                        )
                    )
                elif turn.viewport_intent is not None and (
                    turn.viewport_intent.tighten_relative_to_active
                    or turn.viewport_intent.scope == "preserve_current"
                ):
                    spatial.append(
                        CanonicalSpatialConstraint(
                            relationship="visible_area",
                            target_id=target.target_id,
                            analysis_scope="viewport",
                            provenance="viewport",
                        )
                    )
                else:
                    spatial.append(
                        CanonicalSpatialConstraint(
                            relationship="in"
                            if target.entity_kind != "coordinates"
                            else "at",
                            target_id=target.target_id,
                            analysis_scope=(
                                "point"
                                if target.entity_kind == "coordinates"
                                else "bbox"
                            ),
                            provenance="parser",
                        )
                    )

        data_domains = self._dedupe(
            [*turn.requested_concepts, *turn.requested_layers, *turn.required_data_sources]
        )
        filters: dict[str, Any] = dict(turn.filters)
        # Once compilation has completed, structured extraction fields that
        # affect provider arguments belong to the canonical filter contract.
        # Keeping them here prevents downstream builders from consulting the
        # parser object again and accidentally mixing values from another
        # interpretation.
        if turn.poi_categories:
            filters["poi_categories"] = self._dedupe(turn.poi_categories)
        if turn.entity_target:
            filters["entity_target"] = turn.entity_target
        if turn.requested_attributes:
            filters["attributes"] = self._dedupe(turn.requested_attributes)
        if turn.result_limit is not None:
            filters["limit"] = turn.result_limit
        strongest = re.search(r"\bstrongest\b", turn.user_text, flags=re.IGNORECASE)
        if strongest:
            filters["strength_order"] = "descending"
        ambiguities = list(turn.ambiguities)
        if strongest and not any(
            key in filters
            for key in (
                "magnitude_threshold",
                "min_magnitude",
                "top_n",
                "limit",
            )
        ):
            ambiguities.append("strongest_requires_threshold_or_top_n")
        # A proximity clarification is only meaningful when the parser has
        # explicitly identified a proximity relationship.  Looking for words
        # in raw text here caused unrelated phrases such as "around Times
        # Square" in legacy tool fixtures to be treated as an omitted radius.
        if (
            turn.radius_m is None
            and any(
                item.relationship in {"near", "around", "within_distance"}
                and item.distance_m is None
                for item in turn.geographic_relationships
            )
        ):
            ambiguities.append("spatial_distance_required")
        temporal_text = (turn.temporal_signal.raw_text or "").casefold()
        if (
            "recent" in temporal_text
            and turn.temporal_signal.start_time_iso is None
            and turn.temporal_signal.end_time_iso is None
        ):
            ambiguities.append("recent_requires_time_window")
        if self._is_flood_comparison(turn.operations, data_domains):
            ambiguities.append(FLOOD_COMPARISON_AMBIGUITY)

        temporal_constraints = self._compile_temporal_constraints(
            turn,
            request_datetime=request_datetime,
            client_timezone=client_timezone,
            application_timezone=application_timezone,
        )
        map_required = (
            turn.presentation_mode in {"map", "both"}
            or turn.task_class == "map_search"
        )
        requirements = [
            CompletionRequirement(name="location_resolved", required=turn.normalized_action.requires_location),
            CompletionRequirement(name="required_data_retrieved", required=turn.tools_needed),
            CompletionRequirement(name="spatial_filter_applied", required=bool(spatial)),
            CompletionRequirement(
                name="temporal_filter_applied",
                required=temporal_constraints.mode != "none",
            ),
            CompletionRequirement(name="renderable_geometry_created", required=map_required),
            CompletionRequirement(name="map_state_committed", required=map_required),
            CompletionRequirement(name="viewport_contains_results", required=map_required),
            CompletionRequirement(name="final_response_ready"),
        ]
        assumptions: list[str] = []
        if primary is not None and primary.resolved_location is not None:
            if primary.resolved_location.bbox is not None:
                assumptions.append("Geocoder bounds are used for viewport guidance, not as administrative geometry.")
        if memory_snapshot and turn.relationship in {"follow_up", "clarification"}:
            assumptions.append("Relevant committed task and map state were inherited for this follow-up.")
        if temporal_constraints.resolved_once:
            assumptions.append(
                "Temporal boundaries were resolved once in "
                f"{temporal_constraints.timezone} ({temporal_constraints.timezone_source})."
            )

        return CanonicalRequestInterpretation(
            request_id=request_id,
            relationship_to_previous_turn=relationship,
            primary_intent=turn.normalized_action.action_id,
            operations=self._dedupe(
                [*turn.operations, turn.normalized_action.action_id]
            ),
            targets=targets,
            spatial_constraints=spatial,
            temporal_constraints=temporal_constraints,
            data_domains=data_domains,
            filters=filters,
            presentation=CanonicalPresentation(
                mode=turn.presentation_mode,
                geometry=self._dedupe(
                    [
                        *turn.normalized_action.requested_visualizations,
                        *(
                            str(item)
                            for item in turn.presentation_requirements.get(
                                "geometry", []
                            )
                            if isinstance(item, str)
                        ),
                    ]
                ),
                basemap_id=turn.requested_basemap,
                viewport_operation=(
                    turn.viewport_intent.scope
                    if turn.viewport_intent is not None
                    else "auto"
                ),
                viewport_radius_m=(
                    turn.viewport_intent.radius_hint_m
                    if turn.viewport_intent is not None
                    else None
                ),
                viewport_tighten_relative_to_active=(
                    turn.viewport_intent.tighten_relative_to_active
                    if turn.viewport_intent is not None
                    else False
                ),
                viewport_reason=(
                    turn.viewport_intent.reason
                    if turn.viewport_intent is not None
                    else None
                ),
            ),
            map_required=map_required,
            ambiguities=list(dict.fromkeys(ambiguities)),
            completion_requirements=requirements,
            assumptions=assumptions,
        )

    @staticmethod
    def _key(value: str) -> str:
        return normalize_target_key(value)

    @classmethod
    def _is_flood_comparison(
        cls,
        operations: list[str],
        data_domains: list[str],
    ) -> bool:
        comparison_requested = any(cls._is_comparison_operation(operation) for operation in operations)
        if not comparison_requested:
            return False
        return any(
            any(
                term in cls._key(str(domain))
                for term in cls._FLOOD_COMPARISON_DOMAIN_TERMS
            )
            for domain in data_domains
        )

    @classmethod
    def _is_comparison_operation(cls, operation: str) -> bool:
        operation_key = cls._key(str(operation))
        return (
            operation_key in cls._COMPARISON_OPERATIONS
            or operation_key.startswith("compare ")
            or operation_key.endswith(" compare")
            or "comparison" in operation_key
        )

    @classmethod
    def _compile_temporal_constraints(
        cls,
        turn: TurnParseResult,
        *,
        request_datetime: str | datetime | None,
        client_timezone: str | None,
        application_timezone: str,
    ) -> CanonicalTemporalConstraints:
        temporal = turn.temporal_signal
        zone, zone_name, zone_source = cls._select_timezone(
            client_timezone, application_timezone
        )
        base = cls._coerce_request_datetime(request_datetime).astimezone(zone)
        raw_text = " ".join(
            item.strip()
            for item in (temporal.raw_text or "", turn.user_text)
            if item and item.strip()
        )
        raw_lower = raw_text.casefold()
        start = temporal.start_time_iso
        end = temporal.end_time_iso
        reference = temporal.reference_time_iso
        resolved_once = False

        if not start and not end:
            relative = cls._relative_bounds(raw_lower, base)
            if relative is not None:
                start, end = relative
                resolved_once = True
                if reference is None:
                    reference = base.isoformat()
        if not start and not end:
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", raw_text)
            if dates:
                start = dates[0]
                end = dates[1] if len(dates) > 1 else dates[0]
                resolved_once = True
                if reference is None:
                    reference = base.isoformat()

        normalized_start = cls._normalize_boundary(start, zone, end=False)
        normalized_end = cls._normalize_boundary(
            end,
            zone,
            end=True,
        )
        if normalized_start is not None or normalized_end is not None:
            resolved_once = True

        return CanonicalTemporalConstraints(
            mode=temporal.mode,
            reference_time_iso=(
                cls._normalize_boundary(reference, zone, end=False) or reference
            ),
            start_time_iso=normalized_start,
            end_time_iso=normalized_end,
            granularity=temporal.granularity,
            aggregation=temporal.aggregation,
            raw_text=temporal.raw_text,
            timezone=zone_name,
            timezone_source=zone_source,
            resolved_once=resolved_once,
        )

    @staticmethod
    def _select_timezone(
        client_timezone: str | None,
        application_timezone: str | None,
    ) -> tuple[ZoneInfo, str, Literal["client", "application", "utc"]]:
        for index, candidate in enumerate((client_timezone, application_timezone)):
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            normalized = candidate.strip()
            try:
                source: Literal["client", "application"] = (
                    "client" if index == 0 else "application"
                )
                return ZoneInfo(normalized), normalized, source
            except ZoneInfoNotFoundError:
                continue
        return ZoneInfo("UTC"), "UTC", "utc"

    @staticmethod
    def _coerce_request_datetime(value: str | datetime | None) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str) and value.strip():
            try:
                result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                result = datetime.now(UTC)
        else:
            result = datetime.now(UTC)
        if result.tzinfo is None:
            return result.replace(tzinfo=UTC)
        return result

    @staticmethod
    def _relative_bounds(raw_text: str, base: datetime) -> tuple[str, str] | None:
        local_date = base.date()
        if re.search(r"\btoday\b", raw_text):
            start = datetime.combine(local_date, datetime.min.time(), base.tzinfo)
            return start.isoformat(), (start + timedelta(days=1)).isoformat()
        if re.search(r"\byesterday\b", raw_text):
            end = datetime.combine(local_date, datetime.min.time(), base.tzinfo)
            start = end - timedelta(days=1)
            return start.isoformat(), end.isoformat()
        if re.search(r"\btomorrow\b", raw_text):
            start = datetime.combine(local_date, datetime.min.time(), base.tzinfo) + timedelta(days=1)
            return start.isoformat(), (start + timedelta(days=1)).isoformat()
        if re.search(r"\b(?:this|current)\s+week\b", raw_text):
            start = datetime.combine(local_date, datetime.min.time(), base.tzinfo) - timedelta(
                days=local_date.weekday()
            )
            return start.isoformat(), (start + timedelta(days=7)).isoformat()
        if re.search(r"\blast\s+week\b", raw_text):
            end = datetime.combine(local_date, datetime.min.time(), base.tzinfo) - timedelta(
                days=local_date.weekday()
            )
            start = end - timedelta(days=7)
            return start.isoformat(), end.isoformat()
        match = re.search(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", raw_text)
        if match:
            days = int(match.group(1))
            if days > 0:
                return (base - timedelta(days=days)).isoformat(), base.isoformat()
        return None

    @staticmethod
    def _normalize_boundary(
        value: str | None,
        zone: ZoneInfo,
        *,
        end: bool,
    ) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        else:
            parsed = parsed.astimezone(zone)
        if end and len(text) == 10:
            parsed += timedelta(days=1)
        return parsed.isoformat()

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in values if item and item.strip()))
