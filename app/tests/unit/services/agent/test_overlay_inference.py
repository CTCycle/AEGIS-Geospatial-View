from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.overlay_inference import OverlayInferenceService


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


def _location() -> ResolvedLocation:
    return ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5, confidence=0.9)


def test_overlay_inference_matches_traffic_intent() -> None:
    result = OverlayInferenceService().infer_overlays(
        turn_contract=_turn("Show Paris with traffic"),
        location=_location(),
        existing_overlay_ids=[],
    )

    assert "tomtom_traffic_flow" in result.overlay_ids
    assert "tomtom_traffic_flow" in result.reasons


def test_overlay_inference_matches_precipitation_intent() -> None:
    result = OverlayInferenceService().infer_overlays(
        turn_contract=_turn("Show current rain around Zurich"),
        location=_location(),
        existing_overlay_ids=[],
    )

    assert "rainviewer_precipitation_radar" in result.overlay_ids


def test_overlay_inference_matches_air_quality_intent() -> None:
    result = OverlayInferenceService().infer_overlays(
        turn_contract=_turn("Show Paris with air quality"),
        location=_location(),
        existing_overlay_ids=[],
    )

    assert "openaq_air_quality" in result.overlay_ids


def test_overlay_inference_respects_existing_overlays() -> None:
    result = OverlayInferenceService().infer_overlays(
        turn_contract=_turn("Show Rome with traffic and rain"),
        location=_location(),
        existing_overlay_ids=["tomtom_traffic_flow"],
    )

    assert "tomtom_traffic_flow" not in result.overlay_ids
    assert "rainviewer_precipitation_radar" in result.overlay_ids
