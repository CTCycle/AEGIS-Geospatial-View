"""Build renderer-safe map candidates from typed agent actions."""

from __future__ import annotations

from datetime import UTC, datetime
from math import cos, radians
from typing import Any
from uuid import uuid4

from server.common.typing import json_object
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    ViewportPolicy,
)
from server.domain.agent.evidence import AgentEvidenceEnvelope
from server.domain.agent.map_plan import (
    AddEvidenceLayerAction,
    KeepOnlyLayersAction,
    MapAction,
    RemoveLayerAction,
    SetBasemapAction,
    SetLayerOpacityAction,
    SetLayerVisibilityAction,
    SetViewportAction,
)
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.overlay_collection import OverlayCollectionService
from server.services.geospatial.capability_registry import CapabilityRegistry

###############################################################################
class MapPlanBuildError(ValueError):

    # -------------------------------------------------------------------------
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

###############################################################################
class MapSessionBuilder:
    """Turn catalog descriptors and evidence references into a MapSession."""

    # -------------------------------------------------------------------------
    def __init__(self, *, capability_registry: CapabilityRegistry) -> None:
        self.capability_registry = capability_registry

    # -------------------------------------------------------------------------
    async def build(
        self,
        *,
        location: ResolvedLocation,
        evidence: list[AgentEvidenceEnvelope],
        active_session: MapSession | None,
        actions: list[MapAction],
    ) -> MapSession:
        evidence_by_ref = {
            item.evidence_ref: item for item in evidence if item.evidence_ref
        }
        candidate = self._initial_session(location, active_session, actions)
        for action in actions:
            candidate = self._apply_action(
                candidate,
                action,
                evidence_by_ref=evidence_by_ref,
            )
        return candidate.model_copy(
            update={"session_id": f"candidate-{uuid4().hex}"},
            deep=True,
        )

    # -------------------------------------------------------------------------
    def _initial_session(
        self,
        location: ResolvedLocation,
        active_session: MapSession | None,
        actions: list[MapAction],
    ) -> MapSession:
        if active_session is not None:
            return active_session.model_copy(deep=True)
        basemap_action = next(
            (action for action in actions if isinstance(action, SetBasemapAction)),
            None,
        )
        if basemap_action is None:
            raise MapPlanBuildError(
                "missing_basemap",
                "A new map candidate requires a set_basemap action.",
            )
        basemap = self._capability_descriptor(basemap_action.capability_id)
        viewport = _viewport_for_location(location)
        return MapSession(
            session_id=f"candidate-{uuid4().hex}",
            resolved_location=location,
            basemap_id=basemap_action.capability_id,
            viewport=viewport,
            generated_at=datetime.now(UTC),
            payload={"map_candidate": True},
            center={
                "latitude": viewport.center_latitude,
                "longitude": viewport.center_longitude,
            },
            bounds=viewport.bbox,
            basemap=basemap,
            overlay_collection=OverlayCollectionState(),
        )

    # -------------------------------------------------------------------------
    def _apply_action(
        self,
        session: MapSession,
        action: MapAction,
        *,
        evidence_by_ref: dict[str, AgentEvidenceEnvelope],
    ) -> MapSession:
        if isinstance(action, SetBasemapAction):
            return session.model_copy(
                update={
                    "basemap_id": action.capability_id,
                    "basemap": self._capability_descriptor(action.capability_id),
                },
                deep=True,
            )
        if isinstance(action, AddEvidenceLayerAction):
            evidence = evidence_by_ref.get(action.evidence_ref)
            if evidence is None:
                raise MapPlanBuildError(
                    "unknown_evidence",
                    f"Evidence '{action.evidence_ref}' is not available to the map plan.",
                )
            if evidence.status == "failed":
                raise MapPlanBuildError(
                    "failed_evidence",
                    f"Evidence '{action.evidence_ref}' failed and cannot be rendered.",
                )
            descriptor = self._capability_descriptor(action.capability_id)
            descriptor.update(
                {
                    "id": f"evidence:{action.evidence_ref}:{action.capability_id}",
                    "instance_id": f"evidence:{action.evidence_ref}:{action.capability_id}",
                    "capability_id": action.capability_id,
                    "evidence_ref": action.evidence_ref,
                    "evidence_status": evidence.status,
                    "visible": action.visible,
                    "default_opacity": action.opacity,
                }
            )
            additions = OverlayCollectionService.from_rendered_descriptors(
                [descriptor],
                resolved_location=session.resolved_location,
                viewport=session.viewport,
                revision=session.overlay_collection.revision,
            )
            collection = OverlayCollectionService.merge_instances(
                session.overlay_collection,
                additions.instances,
            )
            return OverlayCollectionService.merge_into_map_session(session, collection)
        if isinstance(action, SetLayerVisibilityAction):
            return self._update_instance(
                session,
                action.instance_id,
                lambda instance: instance.model_copy(
                    update={"visible": action.visible}, deep=True
                ),
            )
        if isinstance(action, SetLayerOpacityAction):
            return self._update_instance(
                session,
                action.instance_id,
                lambda instance: instance.model_copy(
                    update={"opacity": action.opacity}, deep=True
                ),
            )
        if isinstance(action, RemoveLayerAction):
            instances = session.overlay_collection.instances
            if not any(item.instance_id == action.instance_id for item in instances):
                raise MapPlanBuildError(
                    "unknown_layer",
                    f"Layer '{action.instance_id}' is not in the active map.",
                )
            collection = session.overlay_collection.model_copy(
                update={
                    "instances": [
                        item
                        for item in instances
                        if item.instance_id != action.instance_id
                    ],
                    "revision": session.overlay_collection.revision + 1,
                },
                deep=True,
            )
            return OverlayCollectionService.merge_into_map_session(session, collection)
        if isinstance(action, KeepOnlyLayersAction):
            current_ids = {item.instance_id for item in session.overlay_collection.instances}
            missing = sorted(set(action.instance_ids) - current_ids)
            if missing:
                raise MapPlanBuildError(
                    "unknown_layer",
                    f"Layer '{missing[0]}' is not in the active map.",
                )
            kept = [
                item
                for item in session.overlay_collection.instances
                if item.instance_id in set(action.instance_ids)
            ]
            if len(kept) == len(session.overlay_collection.instances):
                return session
            collection = session.overlay_collection.model_copy(
                update={
                    "instances": kept,
                    "revision": session.overlay_collection.revision + 1,
                },
                deep=True,
            )
            return OverlayCollectionService.merge_into_map_session(session, collection)
        if isinstance(action, SetViewportAction):
            if action.strategy == "preserve_current":
                return session
            evidence = [
                evidence_by_ref[ref]
                for ref in action.evidence_refs
                if ref in evidence_by_ref
            ]
            if action.strategy == "fit_evidence":
                bbox = _evidence_bbox(evidence)
                if bbox is not None:
                    viewport = _viewport_for_bbox(bbox, session.viewport)
                    return _with_viewport(session, viewport)
            if action.strategy == "fit_location":
                return _with_viewport(
                    session,
                    _viewport_for_location(session.resolved_location),
                )
            raise MapPlanBuildError(
                "viewport_bounds_unavailable",
                "The requested viewport cannot be derived from validated state.",
            )
        raise MapPlanBuildError("unsupported_action", "The map action is unsupported.")

    # -------------------------------------------------------------------------
    def _update_instance(
        self,
        session: MapSession,
        instance_id: str,
        update: Any,
    ) -> MapSession:
        instances = list(session.overlay_collection.instances)
        for index, instance in enumerate(instances):
            if instance.instance_id == instance_id:
                updated = update(instance)
                if updated == instance:
                    return session
                instances[index] = updated
                collection = session.overlay_collection.model_copy(
                    update={
                        "instances": instances,
                        "revision": session.overlay_collection.revision + 1,
                    },
                    deep=True,
                )
                return OverlayCollectionService.merge_into_map_session(
                    session, collection
                )
        raise MapPlanBuildError(
            "unknown_layer",
            f"Layer '{instance_id}' is not in the active map.",
        )

    # -------------------------------------------------------------------------
    def _capability_descriptor(self, capability_id: str) -> dict[str, Any]:
        capability = self.capability_registry.get_capability(capability_id)
        if capability is None:
            raise MapPlanBuildError(
                "unknown_capability",
                f"Capability '{capability_id}' is not in the validated catalog.",
            )
        metadata = json_object(capability.get("metadata"))
        descriptor = dict(metadata)
        descriptor.update(
            {
                "id": capability_id,
                "capability_id": capability_id,
                "label": str(
                    metadata.get("label")
                    or capability.get("name")
                    or capability_id
                ),
                "provider": str(capability.get("provider") or "unknown"),
                "type": str(
                    capability.get("type")
                    or capability.get("capabilityKind")
                    or "overlay"
                ),
                "rendering_mode": str(
                    capability.get("renderingMode") or "metadata-only"
                ),
            }
        )
        return descriptor


###############################################################################
def _with_viewport(session: MapSession, viewport: ViewportPolicy) -> MapSession:
    return session.model_copy(
        update={
            "viewport": viewport,
            "center": {
                "latitude": viewport.center_latitude,
                "longitude": viewport.center_longitude,
            },
            "bounds": viewport.bbox,
        },
        deep=True,
    )


###############################################################################
def _viewport_for_location(location: ResolvedLocation) -> ViewportPolicy:
    bbox = _valid_bbox(location.bbox)
    return ViewportPolicy(
        center_latitude=location.latitude,
        center_longitude=location.longitude,
        bbox=bbox,
    )


###############################################################################
def _viewport_for_bbox(bbox: list[float], previous: ViewportPolicy) -> ViewportPolicy:
    min_lon, min_lat, max_lon, max_lat = bbox
    center_latitude = (min_lat + max_lat) / 2
    center_longitude = (min_lon + max_lon) / 2
    lat_radius = max(abs(max_lat - min_lat) * 111_320 / 2, 1.0)
    lon_radius = max(
        abs(max_lon - min_lon)
        * 111_320
        * max(abs(cos(radians(center_latitude))), 0.01)
        / 2,
        1.0,
    )
    return ViewportPolicy(
        center_latitude=center_latitude,
        center_longitude=center_longitude,
        radius_m=max(lat_radius, lon_radius, previous.radius_m * 0.1),
        bbox=bbox,
    )


###############################################################################
def _valid_bbox(value: object) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    min_lon, min_lat, max_lon, max_lat = result
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        return None
    return result


###############################################################################
def _evidence_bbox(evidence: list[AgentEvidenceEnvelope]) -> list[float] | None:
    for item in evidence:
        for source in (item.summary, item.provenance):
            for key in ("bbox", "bounds", "analysis_bbox"):
                bbox = _valid_bbox(source.get(key))
                if bbox is not None:
                    return bbox
            coverage = source.get("coverage")
            if isinstance(coverage, dict):
                bbox = _valid_bbox(coverage.get("bbox"))
                if bbox is not None:
                    return bbox
    return None


__all__ = ["MapPlanBuildError", "MapSessionBuilder"]
