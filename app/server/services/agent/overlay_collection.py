"""Deterministic operations over the active map's overlay collection."""

from __future__ import annotations

from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
from collections.abc import Callable
from typing import Any, Iterable, cast
import unicodedata

from server.common.typing import json_array, json_object
from server.contracts.extraction import OverlayCommand, OverlaySelector
from server.contracts.geospatial import (
    MapSession,
    MapInspection,
    OverlayCollectionState,
    OverlayInstance,
    OverlayMutationResult,
    ViewportPolicy,
)
from server.domain.agent.decision import ResolvedLocation


###############################################################################
class OverlayCollectionService:
    """Resolve and apply typed overlay commands without refetching the map.

    The service is intentionally pure: callers provide the current collection
    and an optional catalog.  A new collection is returned only when the
    expected revision matches, which prevents a late tool result from
    overwriting a newer user action.
    """

    # -------------------------------------------------------------------------
    @staticmethod
    def _norm(value: object) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return " ".join(
            "".join(
                character if character.isalnum() else " " for character in text
            ).split()
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _tokens(cls, value: object) -> set[str]:
        normalized = cls._norm(value)
        return {item for item in normalized.split() if item}

    # -------------------------------------------------------------------------
    @classmethod
    def _selector_values(cls, selector: OverlaySelector) -> list[str]:
        return [
            *selector.instance_ids,
            *selector.capability_ids,
            *selector.concepts,
            *selector.labels,
            *selector.providers,
            *selector.overlay_types,
            *selector.rendering_modes,
            *selector.tags,
        ]

    # -------------------------------------------------------------------------
    @classmethod
    def _concept_matches(cls, concepts: set[str], value: str) -> bool:
        normalized = cls._norm(value)
        if not normalized:
            return False
        if normalized in concepts:
            return True
        candidate_tokens: set[str] = set()
        for concept in concepts:
            candidate_tokens.update(cls._tokens(concept))
        return cls._tokens(normalized).issubset(candidate_tokens)

    # -------------------------------------------------------------------------
    @classmethod
    def _metadata_values(cls, metadata: dict[str, Any], *keys: str) -> list[str]:
        values: list[str] = []
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value)
            elif isinstance(value, list):
                values.extend(
                    item.strip()
                    for item in cast(list[Any], value)
                    if isinstance(item, str) and item.strip()
                )
        return list(dict.fromkeys(values))

    # -------------------------------------------------------------------------
    @classmethod
    def _selector_matches_metadata(
        cls,
        selector: OverlaySelector,
        metadata: dict[str, Any],
    ) -> bool:
        """Match a typed selector against a basemap or capability descriptor."""
        if not cls._selector_values(selector):
            return False
        identifiers = {
            cls._norm(value)
            for value in cls._metadata_values(
                metadata, "id", "instance_id", "capability_id", "layer_id"
            )
        }
        if selector.instance_ids and not identifiers.intersection(
            cls._norm(value) for value in selector.instance_ids
        ):
            return False
        if selector.capability_ids and not identifiers.intersection(
            cls._norm(value) for value in selector.capability_ids
        ):
            return False
        semantic_values = cls._metadata_values(
            metadata,
            "id",
            "instance_id",
            "capability_id",
            "layer_id",
            "label",
            "name",
            "type",
            "overlay_type",
            "capabilityKind",
            "capability_kind",
            "concepts",
            "capabilities",
            "tags",
            "aliases",
            "keywords",
        )
        semantic_haystack = {
            cls._norm(value) for value in semantic_values if cls._norm(value)
        }
        if selector.concepts and not any(
            cls._concept_matches(semantic_haystack, value)
            for value in selector.concepts
        ):
            return False
        if selector.labels and not any(
            cls._concept_matches(semantic_haystack, value) for value in selector.labels
        ):
            return False
        if selector.providers:
            providers = {
                cls._norm(value)
                for value in cls._metadata_values(metadata, "provider", "provider_id")
            }
            if not providers.intersection(
                cls._norm(value) for value in selector.providers
            ):
                return False
        if selector.overlay_types:
            types = {
                cls._norm(value)
                for value in cls._metadata_values(
                    metadata, "type", "overlay_type", "kind"
                )
            }
            if not types.intersection(
                cls._norm(value) for value in selector.overlay_types
            ):
                return False
        if selector.rendering_modes:
            modes = {
                cls._norm(value)
                for value in cls._metadata_values(
                    metadata, "rendering_mode", "renderingMode"
                )
            }
            if not modes.intersection(
                cls._norm(value) for value in selector.rendering_modes
            ):
                return False
        if selector.tags:
            tags = {
                cls._norm(value)
                for value in cls._metadata_values(
                    metadata, "tags", "map_type_tags", "action_tags"
                )
            }
            if not any(cls._concept_matches(tags, value) for value in selector.tags):
                return False
        return True

    # -------------------------------------------------------------------------
    @classmethod
    def _instance_concepts(cls, instance: OverlayInstance) -> set[str]:
        descriptor = instance.descriptor
        values: list[object] = [
            instance.capability_id,
            instance.label,
            instance.overlay_type,
            instance.rendering_mode,
        ]
        for key in ("concepts", "tags", "aliases"):
            raw_values = descriptor.get(key)
            if isinstance(raw_values, list):
                raw_values = cast(list[Any], raw_values)
                values.extend(item for item in raw_values if isinstance(item, str))
        flattened: list[object] = []
        for value in values:
            if isinstance(value, list):
                flattened.extend(
                    item for item in cast(list[Any], value) if isinstance(item, str)
                )
            else:
                flattened.append(value)
        return {cls._norm(item) for item in flattened if cls._norm(item)}

    # -------------------------------------------------------------------------
    @classmethod
    def _matches_identity(
        cls, instance: OverlayInstance, selector: OverlaySelector
    ) -> bool:
        if selector.instance_ids and instance.instance_id in selector.instance_ids:
            return True
        if selector.instance_ids:
            return False
        if (
            selector.capability_ids
            and instance.capability_id in selector.capability_ids
        ):
            return True
        if selector.capability_ids:
            return False
        if selector.labels and cls._norm(instance.label) in {
            cls._norm(item) for item in selector.labels
        }:
            return True
        if selector.labels:
            return False
        return True

    # -------------------------------------------------------------------------
    @classmethod
    def _matches_filters(
        cls, instance: OverlayInstance, selector: OverlaySelector
    ) -> bool:
        concepts = cls._instance_concepts(instance)
        # An exact instance/capability identity is authoritative. Parser
        # outputs may include a broad semantic hint alongside the allowlisted
        # capability id (for example ``environmental`` for a hydrography
        # layer); requiring that hint to be repeated in every descriptor makes
        # a valid fetched layer look absent.
        identity_bound = bool(selector.instance_ids or selector.capability_ids)
        if selector.concepts and not identity_bound:
            if not any(
                cls._concept_matches(concepts, value) for value in selector.concepts
            ):
                return False
        if selector.providers and not identity_bound and cls._norm(instance.provider) not in {
            cls._norm(item) for item in selector.providers
        }:
            return False
        if selector.overlay_types and not identity_bound and cls._norm(instance.overlay_type) not in {
            cls._norm(item) for item in selector.overlay_types
        }:
            return False
        if selector.rendering_modes and not identity_bound and cls._norm(instance.rendering_mode) not in {
            cls._norm(item) for item in selector.rendering_modes
        }:
            return False
        if selector.tags and not identity_bound:
            tags = {
                cls._norm(item)
                for item in instance.descriptor.get("tags", [])
                if isinstance(item, str)
            }
            if not tags.intersection({cls._norm(item) for item in selector.tags}):
                return False
        if selector.visibility == "visible" and not instance.visible:
            return False
        if selector.visibility == "hidden" and instance.visible:
            return False
        return True

    # -------------------------------------------------------------------------
    @classmethod
    def _location_point(cls, value: object) -> tuple[float, float] | None:
        if not isinstance(value, dict):
            return None
        location = cast(dict[str, Any], value)
        latitude = location.get("latitude", location.get("center_latitude"))
        longitude = location.get("longitude", location.get("center_longitude"))
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            return float(latitude), float(longitude)
        nested_location = location.get("location")
        if isinstance(nested_location, dict):
            return cls._location_point(cast(dict[str, Any], nested_location))
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _bbox_contains(cls, bbox: object, point: tuple[float, float] | None) -> bool:
        if point is None:
            return False
        values = cls._bbox_values(bbox)
        if values is None:
            return False
        min_lon, min_lat, max_lon, max_lat = values
        latitude, longitude = point
        return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon

    # -------------------------------------------------------------------------
    @staticmethod
    def _bbox_values(value: object) -> tuple[float, float, float, float] | None:
        if not isinstance(value, list):
            return None
        values = cast(list[Any], value)
        if len(values) != 4:
            return None
        numbers: list[float] = []
        for item in values:
            if isinstance(item, (int, float)):
                numbers.append(float(item))
                continue
            if isinstance(item, str):
                try:
                    numbers.append(float(item))
                except ValueError:
                    return None
                continue
            return None
        return tuple(numbers)  # type: ignore[return-value]

    # -------------------------------------------------------------------------
    @classmethod
    def _scope_matches(
        cls,
        instance: OverlayInstance,
        command: OverlayCommand,
        *,
        current_view: dict[str, Any] | None,
    ) -> bool:
        scope = command.scope
        if scope.kind == "global":
            return True
        instance_point = cls._location_point(
            instance.resolved_location.model_dump(mode="json")
            if instance.resolved_location is not None
            else instance.scope
        )
        instance_viewport = instance.viewport or {}
        instance_point = instance_point or cls._location_point(instance_viewport)
        if scope.kind == "current_view":
            view = current_view or {}
            view_bbox = view.get("bbox")
            if cls._bbox_contains(view_bbox, instance_point):
                return True
            instance_bbox = instance_viewport.get("bbox")
            if view_bbox is not None and instance_bbox is not None:
                return cls._bboxes_intersect(view_bbox, instance_bbox)
            if view_bbox is not None:
                return False
            view_point = cls._location_point(view)
            if view_point is None or instance_point is None:
                return False
            view_radius = view.get("radius_m")
            if isinstance(view_radius, (int, float)) and view_radius > 0:
                instance_radius = instance_viewport.get("radius_m")
                padding = (
                    float(instance_radius)
                    if isinstance(instance_radius, (int, float)) and instance_radius > 0
                    else 0.0
                )
                return cls._distance_m(view_point, instance_point) <= float(
                    view_radius
                ) + padding
            return view_point == instance_point
        target = scope.location or {}
        target_bbox = target.get("bbox")
        if cls._bbox_contains(target_bbox, instance_point):
            return True
        target_point = cls._location_point(target)
        if target_point is not None and instance_point is not None:
            target_radius = target.get("radius_m")
            instance_radius = (
                instance.viewport.get("radius_m") if instance.viewport else None
            )
            if isinstance(target_radius, (int, float)) and target_radius > 0:
                return cls._distance_m(target_point, instance_point) <= float(
                    target_radius
                )
            if isinstance(instance_radius, (int, float)) and instance_radius > 0:
                return cls._distance_m(target_point, instance_point) <= float(
                    instance_radius
                )
            return target_point == instance_point
        target_label_value = scope.label
        if not target_label_value:
            target_label_value = target.get("label") or target.get("raw_value")
        target_label = cls._norm(target_label_value)
        if not target_label:
            return False
        instance_labels = {
            cls._norm(instance.scope_key),
            cls._norm(instance.scope.get("label")),
            cls._norm(
                instance.resolved_location.label if instance.resolved_location else ""
            ),
            cls._norm(
                instance.resolved_location.country if instance.resolved_location else ""
            ),
            cls._norm(
                instance.resolved_location.city if instance.resolved_location else ""
            ),
        }
        return target_label in instance_labels

    # -------------------------------------------------------------------------
    @staticmethod
    def _distance_m(
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        earth_radius_m = 6_371_000.0
        left_lat, left_lon = map(radians, left)
        right_lat, right_lon = map(radians, right)
        delta_lat = right_lat - left_lat
        delta_lon = right_lon - left_lon
        haversine = (
            sin(delta_lat / 2) ** 2
            + cos(left_lat) * cos(right_lat) * sin(delta_lon / 2) ** 2
        )
        return 2 * earth_radius_m * asin(sqrt(haversine))

    # -------------------------------------------------------------------------
    @staticmethod
    def _bboxes_intersect(left: object, right: object) -> bool:
        left_values = OverlayCollectionService._bbox_values(left)
        right_values = OverlayCollectionService._bbox_values(right)
        if left_values is None or right_values is None:
            return False
        l_min_lon, l_min_lat, l_max_lon, l_max_lat = left_values
        r_min_lon, r_min_lat, r_max_lon, r_max_lat = right_values
        return not (
            l_max_lon < r_min_lon
            or r_max_lon < l_min_lon
            or l_max_lat < r_min_lat
            or r_max_lat < l_min_lat
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _matching_instances(
        cls,
        collection: OverlayCollectionState,
        command: OverlayCommand,
        *,
        current_view: dict[str, Any] | None,
    ) -> list[OverlayInstance]:
        selector = command.selector
        identity_candidates = list(collection.instances)
        # Resolve identity dimensions by priority, but only commit to a tier
        # when it produces an active match. Model outputs can carry a
        # capability ID in the instance slot; an unmatched stale instance ID
        # must not prevent the valid capability/label tier from resolving.
        identity_matchers: tuple[
            tuple[list[str], Callable[[OverlayInstance], bool]], ...
        ] = (
            (
                selector.instance_ids,
                lambda instance: instance.instance_id in selector.instance_ids,
            ),
            (
                selector.capability_ids,
                lambda instance: instance.capability_id in selector.capability_ids,
            ),
            (
                selector.labels,
                lambda instance: (
                    cls._norm(instance.label)
                    in {cls._norm(value) for value in selector.labels}
                ),
            ),
        )
        for values, matcher in identity_matchers:
            if not values:
                continue
            matches = [
                instance for instance in identity_candidates if matcher(instance)
            ]
            if matches:
                identity_candidates = matches
                break
        return [
            instance
            for instance in identity_candidates
            if cls._matches_filters(instance, selector)
            and cls._scope_matches(instance, command, current_view=current_view)
        ]

    # -------------------------------------------------------------------------
    @classmethod
    def _variant(cls, command: OverlayCommand) -> dict[str, str | None]:
        patch = command.patch
        return {
            "time": patch.time,
            "style": patch.style,
            "format": patch.format,
        }

    # -------------------------------------------------------------------------
    @classmethod
    def _scope_key(cls, command: OverlayCommand) -> str:
        if command.scope.kind == "global":
            return "global"
        if command.scope.kind == "current_view":
            return "current_view"
        location = command.scope.location or {}
        label = (
            location.get("label") or location.get("raw_value") or command.scope.label
        )
        point = cls._location_point(location)
        if point is not None:
            return f"location:{cls._norm(label)}:{point[0]:.4f}:{point[1]:.4f}"
        return f"location:{cls._norm(label)}"

    # -------------------------------------------------------------------------
    @classmethod
    def _stable_id(
        cls, capability_id: str, scope_key: str, variant: dict[str, str | None]
    ) -> str:
        seed = "|".join(
            [
                capability_id,
                scope_key,
                *(f"{key}={variant.get(key) or ''}" for key in sorted(variant)),
            ]
        )
        return f"overlay-{sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    # -------------------------------------------------------------------------
    @classmethod
    def _catalog_candidates(
        cls,
        command: OverlayCommand,
        catalog: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in catalog:
            capability_id = str(item.get("capability_id") or item.get("id") or "")
            label = str(item.get("label") or item.get("name") or capability_id)
            provider = str(item.get("provider") or "")
            overlay_type = str(
                item.get("overlay_type")
                or item.get("type")
                or item.get("kind")
                or "overlay"
            )
            rendering_mode = str(
                item.get("rendering_mode")
                or item.get("renderingMode")
                or "metadata-only"
            )
            concepts = [
                value
                for value in json_array(item.get("concepts"))
                if isinstance(value, str)
            ]
            descriptor = item.get("descriptor")
            descriptor_values = json_object(descriptor)
            tag_values: list[str] = []
            for key in ("tags", "action_tags", "map_type_tags"):
                raw_values = item.get(key)
                tag_values.extend(
                    value
                    for value in json_array(raw_values)
                    if isinstance(value, str)
                )
                tag_values.extend(
                    value
                    for value in json_array(descriptor_values.get(key))
                    if isinstance(value, str)
                )
            raw_metadata = item.get("metadata")
            metadata_values = json_object(raw_metadata)
            for metadata_key in (
                "keywords",
                "action_tags",
                "task_tags",
                "capabilities",
            ):
                tag_values.extend(
                    value
                    for value in json_array(metadata_values.get(metadata_key))
                    if isinstance(value, str)
                )
            concepts.extend(
                value
                for value in json_array(descriptor_values.get("concepts"))
                if isinstance(value, str)
            )
            concepts.extend(tag_values)
            concepts = list(dict.fromkeys(concepts))
            haystack = {
                cls._norm(capability_id),
                cls._norm(label),
                cls._norm(provider),
                cls._norm(overlay_type),
                *[cls._norm(value) for value in concepts],
            }
            label_haystack = {
                cls._norm(capability_id),
                cls._norm(label),
                *[cls._norm(value) for value in concepts],
            }
            selector = command.selector
            if selector.capability_ids and cls._norm(capability_id) not in {
                cls._norm(value) for value in selector.capability_ids
            }:
                continue
            identity_bound = bool(selector.instance_ids or selector.capability_ids)
            if selector.providers and not identity_bound and cls._norm(provider) not in {
                cls._norm(value) for value in selector.providers
            }:
                continue
            if selector.overlay_types and not identity_bound and cls._norm(overlay_type) not in {
                cls._norm(value) for value in selector.overlay_types
            }:
                continue
            if selector.rendering_modes and not identity_bound and cls._norm(rendering_mode) not in {
                cls._norm(value) for value in selector.rendering_modes
            }:
                continue
            if selector.tags and not identity_bound:
                candidate_tags = {
                    cls._norm(value)
                    for value in (*tag_values, *concepts, label)
                    if cls._norm(value)
                }
                if not any(
                    cls._concept_matches(candidate_tags, value)
                    for value in selector.tags
                ):
                    continue
            if selector.concepts and not identity_bound and not any(
                cls._concept_matches(haystack, value) for value in selector.concepts
            ):
                continue
            if selector.labels and not identity_bound and not any(
                cls._concept_matches(label_haystack, value) for value in selector.labels
            ):
                continue
            candidates.append(
                {
                    **item,
                    "capability_id": capability_id,
                    "label": label,
                    "provider": provider,
                    "overlay_type": overlay_type,
                    "rendering_mode": rendering_mode,
                }
            )
        return candidates

    # -------------------------------------------------------------------------
    @classmethod
    def _instance_from_catalog(
        cls,
        command: OverlayCommand,
        candidate: dict[str, Any],
    ) -> OverlayInstance:
        scope_key = cls._scope_key(command)
        variant = cls._variant(command)
        instance_id = cls._stable_id(
            str(candidate["capability_id"]), scope_key, variant
        )
        descriptor = dict(candidate.get("descriptor") or {})
        descriptor.setdefault("id", instance_id)
        descriptor.setdefault("capability_id", candidate["capability_id"])
        descriptor.setdefault("label", candidate["label"])
        descriptor.setdefault("provider", candidate["provider"])
        descriptor.setdefault("type", candidate["overlay_type"])
        descriptor.setdefault("rendering_mode", candidate["rendering_mode"])
        for key in ("concepts", "tags", "aliases"):
            if key in candidate:
                descriptor.setdefault(key, candidate[key])
        descriptor.update(
            {key: value for key, value in variant.items() if value is not None}
        )
        resolved_location = candidate.get("resolved_location")
        return OverlayInstance(
            instance_id=instance_id,
            capability_id=str(candidate["capability_id"]),
            label=str(candidate["label"]),
            provider=str(candidate["provider"]),
            overlay_type=str(candidate["overlay_type"]),
            rendering_mode=str(candidate["rendering_mode"]),
            scope_key=scope_key,
            scope=dict(command.scope.model_dump(mode="json")),
            resolved_location=resolved_location,
            viewport=candidate.get("viewport")
            if isinstance(candidate.get("viewport"), dict)
            else None,
            opacity=command.patch.opacity if command.patch.opacity is not None else 1.0,
            render_variant=variant,
            descriptor=descriptor,
            inspections=list(candidate.get("inspections") or []),
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _unmatched_label(cls, command: OverlayCommand) -> str:
        values = cls._selector_values(command.selector)
        return ", ".join(values) if values else "the requested overlay"

    # -------------------------------------------------------------------------
    @classmethod
    def apply(
        cls,
        collection: OverlayCollectionState,
        command: OverlayCommand,
        *,
        catalog: Iterable[dict[str, Any]] = (),
        current_view: dict[str, Any] | None = None,
        basemap: dict[str, Any] | None = None,
    ) -> tuple[OverlayCollectionState, OverlayMutationResult]:
        expected = command.state_reference.revision
        if expected != collection.revision:
            result = OverlayMutationResult(
                collection_id=collection.collection_id,
                revision=collection.revision,
                clarification=(
                    "The active overlay map changed while this request was running. "
                    "Please retry the overlay change against the current map."
                ),
            )
            return collection.model_copy(deep=True), result

        instances = [item.model_copy(deep=True) for item in collection.instances]
        added: list[str] = []
        removed: list[str] = []
        updated: list[str] = []
        unmatched: list[str] = []
        ambiguous: list[str] = []

        matches = cls._matching_instances(
            collection, command, current_view=current_view
        )
        # A global command without an independent overlay selector is not
        # deterministic: its scope would otherwise turn into "all overlays".
        # An explicit geographic/current-view scope is meaningful because the
        # request is intentionally operating on every instance in that scope.
        if (
            not cls._selector_values(command.selector)
            and command.scope.kind == "global"
            and command.action in {"remove", "show", "hide", "update"}
        ):
            matches = []
            ambiguous.append(cls._unmatched_label(command))
        if command.action == "keep_only" and not cls._selector_values(command.selector):
            matches = []
        if command.action in {"add", "show"} and not matches:
            candidates = cls._catalog_candidates(command, catalog)
            if len(candidates) == 1:
                instance = cls._instance_from_catalog(command, candidates[0])
                existing_index = next(
                    (
                        index
                        for index, item in enumerate(instances)
                        if item.instance_id == instance.instance_id
                    ),
                    None,
                )
                if existing_index is None:
                    instances.append(instance)
                    added.append(instance.instance_id)
                else:
                    # Re-adding an existing scoped capability is an unhide,
                    # not a provider refresh. Preserve its descriptor and
                    # inspection payload byte-for-byte unless a presentation
                    # patch actually changes it.
                    existing = instances[existing_index]
                    changed = not existing.visible
                    if changed:
                        existing.visible = True
                        instances[existing_index] = existing
                        updated.append(existing.instance_id)
                    matches = [existing]
            elif len(candidates) > 1:
                ambiguous.append(cls._unmatched_label(command))
            else:
                unmatched.append(cls._unmatched_label(command))

        if command.action == "keep_only":
            if not matches and not ambiguous:
                unmatched.append(cls._unmatched_label(command))
            else:
                match_ids = {item.instance_id for item in matches}
                kept: list[OverlayInstance] = []
                for instance in instances:
                    if (
                        cls._scope_matches(instance, command, current_view=current_view)
                        and instance.instance_id not in match_ids
                    ):
                        removed.append(instance.instance_id)
                    else:
                        kept.append(instance)
                instances = kept
        elif command.action == "remove":
            if not matches and not ambiguous:
                unmatched.append(cls._unmatched_label(command))
            else:
                match_ids = {item.instance_id for item in matches}
                instances = [
                    item for item in instances if item.instance_id not in match_ids
                ]
                removed.extend(sorted(match_ids))
        elif command.action in {"show", "hide", "update"}:
            if not matches and not added and not ambiguous:
                unmatched.append(cls._unmatched_label(command))
            match_ids = {item.instance_id for item in matches}
            for index, instance in enumerate(instances):
                if instance.instance_id not in match_ids:
                    continue
                changed = False
                if command.action == "show" and not instance.visible:
                    instance.visible = True
                    changed = True
                elif command.action == "hide" and instance.visible:
                    instance.visible = False
                    changed = True
                elif command.action == "update":
                    patch = command.patch
                    if patch.opacity is not None and instance.opacity != patch.opacity:
                        instance.opacity = patch.opacity
                        changed = True
                    variant = cls._variant(command)
                    for key, value in variant.items():
                        if (
                            value is not None
                            and instance.render_variant.get(key) != value
                        ):
                            instance.render_variant[key] = value
                            instance.descriptor[key] = value
                            changed = True
                if changed:
                    instances[index] = instance
                    updated.append(instance.instance_id)

        changed = bool(added or removed or updated)
        next_revision = collection.revision + 1 if changed else collection.revision
        next_collection = collection.model_copy(
            update={"revision": next_revision, "instances": instances},
            deep=True,
        )
        clarification = None
        if ambiguous:
            clarification = "More than one overlay matches the requested selector. Choose a specific overlay."
        elif unmatched:
            if (
                basemap is not None
                and command.action in {"remove", "keep_only", "hide", "update"}
                and cls._selector_matches_metadata(command.selector, basemap)
            ):
                clarification = (
                    "The requested item matches the active map basemap, not an overlay. "
                    "The basemap and active overlays were left unchanged; choose an overlay to modify."
                )
            else:
                clarification = "No existing overlay matches the requested selector; the map was left unchanged."
        return next_collection, OverlayMutationResult(
            collection_id=collection.collection_id,
            revision=next_revision,
            added_instance_ids=added,
            removed_instance_ids=removed,
            updated_instance_ids=sorted(set(updated)),
            unmatched_selectors=unmatched,
            ambiguous_selectors=ambiguous,
            clarification=clarification,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def apply_commands(
        cls,
        collection: OverlayCollectionState,
        commands: Iterable[OverlayCommand],
        *,
        catalog: Iterable[dict[str, Any]] = (),
        current_view: dict[str, Any] | None = None,
        basemap: dict[str, Any] | None = None,
    ) -> tuple[OverlayCollectionState, list[OverlayMutationResult]]:
        current = collection.model_copy(deep=True)
        results: list[OverlayMutationResult] = []
        for command in commands:
            if command.state_reference.revision == 0 and current.revision > 0:
                command = command.model_copy(
                    update={
                        "state_reference": command.state_reference.model_copy(
                            update={"revision": current.revision}
                        )
                    }
                )
            current, result = cls.apply(
                current,
                command,
                catalog=catalog,
                current_view=current_view,
                basemap=basemap,
            )
            results.append(result)
        return current, results

    # -------------------------------------------------------------------------
    @classmethod
    def has_matching_instances(
        cls,
        collection: OverlayCollectionState,
        command: OverlayCommand,
        *,
        current_view: dict[str, Any] | None = None,
    ) -> bool:
        """Return whether a command can be satisfied from active state alone."""
        return bool(
            cls._matching_instances(collection, command, current_view=current_view)
        )

    # -------------------------------------------------------------------------
    @classmethod
    def can_apply_locally(
        cls,
        collection: OverlayCollectionState,
        commands: Iterable[OverlayCommand],
        *,
        current_view: dict[str, Any] | None = None,
    ) -> bool:
        """Return whether every command can be satisfied from active state.

        Removal, visibility, and presentation-only updates operate on the
        authoritative collection.  Adding a missing overlay, or changing a
        provider-backed variant, still requires the normal provider path.
        """

        command_list = list(commands)
        return bool(command_list) and len(
            cls.locally_applicable_commands(
                collection,
                command_list,
                current_view=current_view,
            )
        ) == len(command_list)

    # -------------------------------------------------------------------------
    @classmethod
    def locally_applicable_commands(
        cls,
        collection: OverlayCollectionState,
        commands: Iterable[OverlayCommand],
        *,
        current_view: dict[str, Any] | None = None,
    ) -> list[OverlayCommand]:
        """Select commands that need no provider fetch from active state."""

        applicable: list[OverlayCommand] = []
        for command in commands:
            if command.action in {"remove", "keep_only", "hide"}:
                applicable.append(command)
                continue
            if command.action not in {"show", "update"}:
                continue
            if not cls.has_matching_instances(
                collection,
                command,
                current_view=current_view,
            ):
                continue
            if command.action == "update" and any(
                value is not None
                for value in (
                    command.patch.time,
                    command.patch.style,
                    command.patch.format,
                )
            ):
                continue
            applicable.append(command)
        return applicable

    # -------------------------------------------------------------------------
    @classmethod
    def from_rendered_descriptors(
        cls,
        descriptors: Iterable[dict[str, object]],
        *,
        resolved_location: ResolvedLocation,
        viewport: ViewportPolicy,
        revision: int = 0,
    ) -> OverlayCollectionState:
        """Create the authoritative collection for a newly rendered map."""
        location_label = resolved_location.label.strip() or "map"
        session_scope_key = (
            f"location:{cls._norm(location_label)}:"
            f"{resolved_location.latitude:.4f}:{resolved_location.longitude:.4f}"
        )
        instances: list[OverlayInstance] = []
        for raw_descriptor in descriptors:
            descriptor = dict(raw_descriptor)
            overlay_id = str(descriptor.get("id") or descriptor.get("layer_id") or "")
            if not overlay_id:
                continue
            capability_id = str(descriptor.get("capability_id") or overlay_id)
            render_payload = json_object(descriptor.get("render"))
            variant = {
                key: (
                    str(descriptor[key])
                    if descriptor.get(key) is not None
                    else (
                        str(render_payload[key])
                        if render_payload.get(key) is not None
                        else None
                    )
                )
                for key in ("time", "style", "format")
            }
            instance_id = str(
                descriptor.get("instance_id")
                or cls._stable_id(capability_id, session_scope_key, variant)
            )
            descriptor["id"] = instance_id
            descriptor["instance_id"] = instance_id
            descriptor["capability_id"] = capability_id
            label = str(descriptor.get("label") or overlay_id)
            provider = str(descriptor.get("provider") or "unknown")
            overlay_type = str(descriptor.get("type") or "overlay")
            rendering_mode = str(
                descriptor.get("rendering_mode")
                or render_payload.get("rendering_mode")
                or overlay_type
                or "metadata-only"
            )
            raw_inspections = descriptor.get("inspections")
            inspections: list[MapInspection] = []
            if isinstance(raw_inspections, list):
                for raw_inspection in cast(list[Any], raw_inspections):
                    if not isinstance(raw_inspection, dict):
                        continue
                    try:
                        inspections.append(MapInspection.model_validate(raw_inspection))
                    except Exception:  # noqa: BLE001
                        continue
            raw_opacity = descriptor.get("default_opacity")
            opacity = (
                float(raw_opacity) if isinstance(raw_opacity, (int, float)) else 1.0
            )
            instances.append(
                OverlayInstance(
                    instance_id=instance_id,
                    capability_id=capability_id,
                    label=label,
                    provider=provider,
                    overlay_type=overlay_type,
                    rendering_mode=rendering_mode,
                    scope_key=session_scope_key,
                    scope={"kind": "location", "label": location_label},
                    resolved_location=resolved_location,
                    viewport=viewport.model_dump(mode="json"),
                    visible=descriptor.get("visible") is not False,
                    opacity=opacity,
                    render_variant=variant,
                    descriptor=descriptor,
                    inspections=inspections,
                )
            )
        return OverlayCollectionState(revision=revision, instances=instances)

    # -------------------------------------------------------------------------
    @staticmethod
    def catalog_from_collection(
        collection: OverlayCollectionState,
    ) -> list[dict[str, Any]]:
        """Expose current descriptors as an add-command catalog."""
        catalog: list[dict[str, Any]] = []
        for instance in collection.instances:
            descriptor = dict(instance.descriptor)
            catalog.append(
                {
                    **descriptor,
                    "id": instance.capability_id,
                    "instance_id": instance.instance_id,
                    "capability_id": instance.capability_id,
                    "label": instance.label,
                    "provider": instance.provider,
                    "overlay_type": instance.overlay_type,
                    "rendering_mode": instance.rendering_mode,
                    "visible": instance.visible,
                    "default_opacity": instance.opacity,
                    "descriptor": descriptor,
                }
            )
        return catalog

    # -------------------------------------------------------------------------
    @classmethod
    def from_map_session(
        cls, session: MapSession | dict[str, Any] | None
    ) -> OverlayCollectionState:
        if session is None:
            return OverlayCollectionState()
        model = (
            session
            if isinstance(session, MapSession)
            else MapSession.model_validate(session)
        )
        return model.overlay_collection.model_copy(deep=True)

    # -------------------------------------------------------------------------
    @classmethod
    def merge_into_map_session(
        cls,
        session: MapSession,
        collection: OverlayCollectionState,
    ) -> MapSession:
        """Replace only the authoritative collection in the map session."""
        return session.model_copy(
            update={"overlay_collection": collection},
            deep=True,
        )
