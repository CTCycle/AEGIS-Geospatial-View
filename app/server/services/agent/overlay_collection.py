"""Deterministic operations over the active map's overlay collection."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Iterable, cast

from server.contracts.extraction import OverlayCommand, OverlaySelector
from server.contracts.geospatial import (
    MapSession,
    MapInspection,
    OverlayCollectionState,
    OverlayInstance,
    OverlayMutationResult,
)


class OverlayCollectionService:
    """Resolve and apply typed overlay commands without refetching the map.

    The service is intentionally pure: callers provide the current collection
    and an optional catalog.  A new collection is returned only when the
    expected revision matches, which prevents a late tool result from
    overwriting a newer user action.
    """

    _CONCEPT_ALIASES: dict[str, set[str]] = {
        "weather": {"weather", "forecast", "temperature", "wind"},
        "precipitation": {"precipitation", "rain", "rainfall"},
        "air quality": {"air quality", "air_quality", "pollution", "aqi"},
        "satellite": {"satellite", "imagery", "remote sensing"},
        "active fire": {"active fire", "active_fire", "fires", "fire"},
        "land cover": {"land cover", "land_cover", "landuse", "land use"},
    }

    # ------------------------------------------------------------------
    @staticmethod
    def _norm(value: object) -> str:
        text = " ".join(str(value or "").casefold().split())
        return "".join(character for character in text if character.isalnum() or character == " ")

    # ------------------------------------------------------------------
    @classmethod
    def _tokens(cls, value: object) -> set[str]:
        normalized = cls._norm(value)
        return {item for item in normalized.replace("_", " ").split() if item}

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    @classmethod
    def _aliases_for(cls, value: str) -> set[str]:
        normalized = cls._norm(value)
        aliases = {normalized}
        for canonical, variants in cls._CONCEPT_ALIASES.items():
            if normalized == cls._norm(canonical) or normalized in {cls._norm(item) for item in variants}:
                aliases.update(cls._norm(item) for item in variants)
                aliases.add(cls._norm(canonical))
        return aliases

    # ------------------------------------------------------------------
    @classmethod
    def _concept_matches(cls, concepts: set[str], value: str) -> bool:
        aliases = cls._aliases_for(value)
        concept_tokens: set[str] = set()
        for concept in concepts:
            concept_tokens.update(cls._tokens(concept))
        return any(
            alias in concepts
            or any(alias in concept or concept in alias for concept in concepts)
            or cls._tokens(alias).issubset(concept_tokens)
            for alias in aliases
        )

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
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
        semantic_haystack = {cls._norm(value) for value in semantic_values if cls._norm(value)}
        if selector.concepts and not any(
            cls._concept_matches(semantic_haystack, value) for value in selector.concepts
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
            if not providers.intersection(cls._norm(value) for value in selector.providers):
                return False
        if selector.overlay_types:
            types = {
                cls._norm(value)
                for value in cls._metadata_values(metadata, "type", "overlay_type", "kind")
            }
            if not types.intersection(cls._norm(value) for value in selector.overlay_types):
                return False
        if selector.rendering_modes:
            modes = {
                cls._norm(value)
                for value in cls._metadata_values(metadata, "rendering_mode", "renderingMode")
            }
            if not modes.intersection(cls._norm(value) for value in selector.rendering_modes):
                return False
        if selector.tags:
            tags = {
                cls._norm(value)
                for value in cls._metadata_values(metadata, "tags", "map_type_tags", "action_tags")
            }
            if not any(cls._concept_matches(tags, value) for value in selector.tags):
                return False
        return True

    # ------------------------------------------------------------------
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
                flattened.extend(item for item in cast(list[Any], value) if isinstance(item, str))
            else:
                flattened.append(value)
        return {cls._norm(item) for item in flattened if cls._norm(item)}

    # ------------------------------------------------------------------
    @classmethod
    def _matches_identity(cls, instance: OverlayInstance, selector: OverlaySelector) -> bool:
        if selector.instance_ids and instance.instance_id in selector.instance_ids:
            return True
        if selector.instance_ids:
            return False
        if selector.capability_ids and instance.capability_id in selector.capability_ids:
            return True
        if selector.capability_ids:
            return False
        if selector.labels and cls._norm(instance.label) in {cls._norm(item) for item in selector.labels}:
            return True
        if selector.labels:
            return False
        return True

    # ------------------------------------------------------------------
    @classmethod
    def _matches_filters(cls, instance: OverlayInstance, selector: OverlaySelector) -> bool:
        concepts = cls._instance_concepts(instance)
        if selector.concepts:
            if not any(cls._concept_matches(concepts, value) for value in selector.concepts):
                return False
        if selector.providers and cls._norm(instance.provider) not in {
            cls._norm(item) for item in selector.providers
        }:
            return False
        if selector.overlay_types and cls._norm(instance.overlay_type) not in {
            cls._norm(item) for item in selector.overlay_types
        }:
            return False
        if selector.rendering_modes and cls._norm(instance.rendering_mode) not in {
            cls._norm(item) for item in selector.rendering_modes
        }:
            return False
        if selector.tags:
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

    # ------------------------------------------------------------------
    @classmethod
    def _location_point(cls, value: object) -> tuple[float, float] | None:
        if not isinstance(value, dict):
            return None
        location = cast(dict[str, Any], value)
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            return float(latitude), float(longitude)
        return None

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
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
        if scope.kind == "current_view":
            view = current_view or {}
            view_bbox = view.get("bbox")
            if cls._bbox_contains(view_bbox, instance_point):
                return True
            instance_bbox = instance.viewport.get("bbox") if instance.viewport else None
            if view_bbox is not None and instance_bbox is not None:
                return cls._bboxes_intersect(view_bbox, instance_bbox)
            return False
        target = scope.location or {}
        target_bbox = target.get("bbox")
        if cls._bbox_contains(target_bbox, instance_point):
            return True
        target_point = cls._location_point(target)
        if target_point is not None and instance_point is not None:
            return abs(target_point[0] - instance_point[0]) < 0.25 and abs(
                target_point[1] - instance_point[1]
            ) < 0.25
        target_label_value = scope.label
        if not target_label_value:
            target_label_value = target.get("label") or target.get("raw_value")
        target_label = cls._norm(target_label_value)
        if not target_label:
            return False
        instance_labels = {
            cls._norm(instance.scope_key),
            cls._norm(instance.scope.get("label")),
            cls._norm(instance.resolved_location.label if instance.resolved_location else ""),
            cls._norm(instance.resolved_location.country if instance.resolved_location else ""),
            cls._norm(instance.resolved_location.city if instance.resolved_location else ""),
        }
        return target_label in instance_labels

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    @classmethod
    def _matching_instances(
        cls,
        collection: OverlayCollectionState,
        command: OverlayCommand,
        *,
        current_view: dict[str, Any] | None,
    ) -> list[OverlayInstance]:
        return [
            instance
            for instance in collection.instances
            if cls._matches_identity(instance, command.selector)
            and cls._matches_filters(instance, command.selector)
            and cls._scope_matches(instance, command, current_view=current_view)
        ]

    # ------------------------------------------------------------------
    @classmethod
    def _variant(cls, command: OverlayCommand) -> dict[str, str | None]:
        patch = command.patch
        return {
            "time": patch.time,
            "style": patch.style,
            "format": patch.format,
        }

    # ------------------------------------------------------------------
    @classmethod
    def _scope_key(cls, command: OverlayCommand) -> str:
        if command.scope.kind == "global":
            return "global"
        if command.scope.kind == "current_view":
            return "current_view"
        location = command.scope.location or {}
        label = location.get("label") or location.get("raw_value") or command.scope.label
        point = cls._location_point(location)
        if point is not None:
            return f"location:{cls._norm(label)}:{point[0]:.4f}:{point[1]:.4f}"
        return f"location:{cls._norm(label)}"

    # ------------------------------------------------------------------
    @classmethod
    def _stable_id(cls, capability_id: str, scope_key: str, variant: dict[str, str | None]) -> str:
        seed = "|".join(
            [capability_id, scope_key, *(f"{key}={variant.get(key) or ''}" for key in sorted(variant))]
        )
        return f"overlay-{sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    # ------------------------------------------------------------------
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
            overlay_type = str(item.get("overlay_type") or item.get("type") or item.get("kind") or "overlay")
            rendering_mode = str(item.get("rendering_mode") or item.get("renderingMode") or "metadata-only")
            concepts_raw = item.get("concepts")
            concepts = (
                [value for value in cast(list[Any], concepts_raw) if isinstance(value, str)]
                if isinstance(concepts_raw, list)
                else []
            )
            descriptor = item.get("descriptor")
            descriptor_values = descriptor if isinstance(descriptor, dict) else {}
            tag_values: list[str] = []
            for key in ("tags", "action_tags", "map_type_tags"):
                raw_values = item.get(key)
                if isinstance(raw_values, list):
                    tag_values.extend(value for value in cast(list[Any], raw_values) if isinstance(value, str))
                raw_descriptor_values = descriptor_values.get(key)
                if isinstance(raw_descriptor_values, list):
                    tag_values.extend(
                        value
                        for value in cast(list[Any], raw_descriptor_values)
                        if isinstance(value, str)
                    )
            descriptor_concepts = descriptor_values.get("concepts")
            if isinstance(descriptor_concepts, list):
                concepts.extend(
                    value for value in cast(list[Any], descriptor_concepts) if isinstance(value, str)
                )
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
            if selector.capability_ids and capability_id not in selector.capability_ids:
                continue
            if selector.providers and cls._norm(provider) not in {cls._norm(value) for value in selector.providers}:
                continue
            if selector.overlay_types and cls._norm(overlay_type) not in {
                cls._norm(value) for value in selector.overlay_types
            }:
                continue
            if selector.rendering_modes and cls._norm(rendering_mode) not in {
                cls._norm(value) for value in selector.rendering_modes
            }:
                continue
            if selector.tags:
                candidate_tags = {
                    cls._norm(value)
                    for value in (*tag_values, *concepts, label)
                    if cls._norm(value)
                }
                if not any(
                    cls._concept_matches(candidate_tags, value) for value in selector.tags
                ):
                    continue
            if selector.concepts and not any(
                cls._concept_matches(haystack, value) for value in selector.concepts
            ):
                continue
            if selector.labels and not any(
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

    # ------------------------------------------------------------------
    @classmethod
    def _instance_from_catalog(
        cls,
        command: OverlayCommand,
        candidate: dict[str, Any],
    ) -> OverlayInstance:
        scope_key = cls._scope_key(command)
        variant = cls._variant(command)
        instance_id = cls._stable_id(str(candidate["capability_id"]), scope_key, variant)
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
        descriptor.update({key: value for key, value in variant.items() if value is not None})
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
            viewport=candidate.get("viewport") if isinstance(candidate.get("viewport"), dict) else None,
            opacity=command.patch.opacity if command.patch.opacity is not None else 1.0,
            render_variant=variant,
            descriptor=descriptor,
            inspections=list(candidate.get("inspections") or []),
        )

    # ------------------------------------------------------------------
    @classmethod
    def _unmatched_label(cls, command: OverlayCommand) -> str:
        values = cls._selector_values(command.selector)
        return ", ".join(values) if values else "the requested overlay"

    # ------------------------------------------------------------------
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

        matches = cls._matching_instances(collection, command, current_view=current_view)
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
                    if cls._scope_matches(instance, command, current_view=current_view) and instance.instance_id not in match_ids:
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
                        if value is not None and instance.render_variant.get(key) != value:
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

    # ------------------------------------------------------------------
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
            current, result = cls.apply(
                current,
                command,
                catalog=catalog,
                current_view=current_view,
                basemap=basemap,
            )
            results.append(result)
        return current, results

    # ------------------------------------------------------------------
    @classmethod
    def has_matching_instances(
        cls,
        collection: OverlayCollectionState,
        command: OverlayCommand,
        *,
        current_view: dict[str, Any] | None = None,
    ) -> bool:
        """Return whether a command can be satisfied from active state alone."""
        return bool(cls._matching_instances(collection, command, current_view=current_view))

    # ------------------------------------------------------------------
    @classmethod
    def from_map_session(cls, session: MapSession | dict[str, Any] | None) -> OverlayCollectionState:
        if session is None:
            return OverlayCollectionState()
        model = session if isinstance(session, MapSession) else MapSession.model_validate(session)
        if model.overlay_collection is not None:
            return model.overlay_collection.model_copy(deep=True)
        instances: list[OverlayInstance] = []
        location_label = model.resolved_location.label.strip() or "map"
        point = (model.resolved_location.latitude, model.resolved_location.longitude)
        session_scope_key = f"location:{cls._norm(location_label)}:{point[0]:.4f}:{point[1]:.4f}"
        for descriptor in model.overlays:
            overlay_id = str(descriptor.get("id") or descriptor.get("layer_id") or "")
            if not overlay_id:
                continue
            capability_id = str(descriptor.get("capability_id") or overlay_id)
            variant = {
                "time": str(descriptor.get("time")) if descriptor.get("time") is not None else None,
                "style": str(descriptor.get("style")) if descriptor.get("style") is not None else None,
                "format": str(descriptor.get("format")) if descriptor.get("format") is not None else None,
            }
            instance_id = str(descriptor.get("instance_id") or cls._stable_id(capability_id, session_scope_key, variant))
            raw_inspections = descriptor.get("inspections")
            inspections: list[MapInspection] = []
            if isinstance(raw_inspections, list):
                for raw_inspection in cast(list[Any], raw_inspections):
                    if not isinstance(raw_inspection, dict):
                        continue
                    try:
                        inspections.append(MapInspection.model_validate(raw_inspection))
                    except Exception:
                        continue
            instances.append(
                OverlayInstance(
                    instance_id=instance_id,
                    capability_id=capability_id,
                    label=str(descriptor.get("label") or overlay_id),
                    provider=str(descriptor.get("provider") or "unknown"),
                    overlay_type=str(descriptor.get("type") or "overlay"),
                    rendering_mode=str(descriptor.get("rendering_mode") or "metadata-only"),
                    scope_key=session_scope_key,
                    scope={"kind": "location", "label": location_label},
                    resolved_location=model.resolved_location,
                    viewport=model.viewport.model_dump(mode="json"),
                    visible=descriptor.get("visible") is not False,
                    opacity=(
                        float(default_opacity)
                        if isinstance(default_opacity := descriptor.get("default_opacity"), (int, float))
                        else 1.0
                    ),
                    render_variant=variant,
                    descriptor=dict(descriptor),
                    inspections=inspections,
                )
            )
        return OverlayCollectionState(
            revision=model.overlay_collection_revision,
            instances=instances,
        )

    # ------------------------------------------------------------------
    @classmethod
    def merge_into_map_session(
        cls,
        session: MapSession,
        collection: OverlayCollectionState,
    ) -> MapSession:
        """Project the authoritative collection into the existing map session.

        Descriptors are retained verbatim for unchanged instances.  Only the
        presentation fields controlled by a command are changed, so a hide,
        show, or remove operation never causes unrelated providers to run.
        """
        overlays: list[dict[str, Any]] = []
        inspections: list[Any] = []
        for instance in collection.instances:
            descriptor = dict(instance.descriptor)
            descriptor["id"] = instance.instance_id
            descriptor["instance_id"] = instance.instance_id
            descriptor["capability_id"] = instance.capability_id
            descriptor["visible"] = instance.visible
            descriptor["default_opacity"] = instance.opacity
            descriptor.setdefault("label", instance.label)
            descriptor.setdefault("provider", instance.provider)
            descriptor.setdefault("type", instance.overlay_type)
            descriptor.setdefault("rendering_mode", instance.rendering_mode)
            overlays.append(descriptor)
            inspections.extend(instance.inspections)
        return session.model_copy(
            update={
                "overlay_ids": [instance.instance_id for instance in collection.instances],
                "requested_overlay_ids": [instance.instance_id for instance in collection.instances],
                "rendered_overlay_ids": [
                    instance.instance_id for instance in collection.instances if instance.visible
                ],
                "overlays": overlays,
                "overlay_collection_revision": collection.revision,
                "overlay_collection": collection,
                "inspections": inspections,
            },
            deep=True,
        )
