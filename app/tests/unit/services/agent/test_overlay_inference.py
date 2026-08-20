from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.contracts.extraction import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.overlay_inference import OverlayInferenceService
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
def _turn(
    user_text: str,
    *,
    action_id: str = "map_search",
    task_tags: list[str] | None = None,
    action_tags: list[str] | None = None,
) -> TurnParseResult:
    return TurnParseResult(
        user_text=user_text,
        conversation_context=ConversationContextSnapshot(recent_messages=[], memory_snapshot={}),
        task_class="map_search",
        location_signals=[],
        normalized_action=NormalizedAction(
            action_id=action_id,
            action_label=action_id,
            task_tags=task_tags or [],
            action_tags=action_tags or [],
            requires_location=True,
        ),
        parser_confidence=0.9,
    )

###############################################################################
def _location() -> ResolvedLocation:
    return ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5, confidence=0.9)

###############################################################################
class _Credentials:

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN001
        _ = provider, label
        return None

###############################################################################
def _overlay_service() -> OverlayInferenceService:
    return OverlayInferenceService(
        capability_registry=CapabilityRegistry(),
        runtime_registry=RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_Credentials(),  # type: ignore[arg-type]
        ),
    )

###############################################################################
def test_overlay_inference_matches_traffic_intent() -> None:
    result = _overlay_service().infer_overlays(
        turn_contract=_turn("Show Paris with traffic"),
        location=_location(),
        existing_overlay_ids=[],
    )

    assert "tomtom_traffic_flow" in result.overlay_ids
    assert "tomtom_traffic_flow" in result.reasons

###############################################################################
def test_overlay_inference_matches_precipitation_intent() -> None:
    result = _overlay_service().infer_overlays(
        turn_contract=_turn("Show current rain around Zurich"),
        location=_location(),
        existing_overlay_ids=[],
    )

    assert "rainviewer_precipitation_radar" in result.overlay_ids

###############################################################################
def test_overlay_inference_matches_air_quality_intent() -> None:
    result = _overlay_service().infer_overlays(
        turn_contract=_turn("Show Paris with air quality"),
        location=_location(),
        existing_overlay_ids=[],
    )

    assert "openaq_air_quality" in result.overlay_ids

###############################################################################
def test_overlay_inference_does_not_duplicate_existing_air_quality_concept() -> None:
    result = _overlay_service().infer_overlays(
        turn_contract=_turn("Show air quality overlay for Paris"),
        location=_location(),
        existing_overlay_ids=["openmeteo_air_quality_forecast"],
    )

    assert result.overlay_ids == []

###############################################################################
def test_overlay_inference_respects_existing_overlays() -> None:
    result = _overlay_service().infer_overlays(
        turn_contract=_turn("Show Rome with traffic and rain"),
        location=_location(),
        existing_overlay_ids=["tomtom_traffic_flow"],
    )

    assert "tomtom_traffic_flow" not in result.overlay_ids
    assert "rainviewer_precipitation_radar" in result.overlay_ids

###############################################################################
def test_overlay_inference_removes_requested_existing_precipitation_overlay() -> None:
    service = _overlay_service()
    turn = _turn("Remove the precipitation radar from this map")

    removed = service.removed_overlay_ids(
        turn_contract=turn,
        existing_overlay_ids=["rainviewer_precipitation_radar"],
    )
    result = service.infer_overlays(
        turn_contract=turn,
        location=_location(),
        existing_overlay_ids=["rainviewer_precipitation_radar"],
    )

    assert removed == ["rainviewer_precipitation_radar"]
    assert result.overlay_ids == []
