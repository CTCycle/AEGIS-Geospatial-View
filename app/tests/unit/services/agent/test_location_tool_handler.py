from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.tool_definitions import ResolveLocationInput
from server.services.agent.tool_handlers.location import LocationToolHandler

###############################################################################
@pytest.mark.asyncio
async def test_coordinate_query_is_resolved_without_geocoder_egress() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show 46.0037, 8.9511.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(
            query="46.0037, 8.9511",
            expected_location_type="coordinates",
        ),
        state,
    )

    assert result.status == "success"
    location = state.location_refs["46.0037, 8.9511"]
    assert location.latitude == 46.0037
    assert location.longitude == 8.9511

###############################################################################
@pytest.mark.asyncio
async def test_invalid_coordinate_query_is_rejected_with_bounds() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Go to 91, 181.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(query="91, 181", expected_location_type="coordinates"),
        state,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_coordinates"
    assert result.data == {
        "resolution_status": "invalid_coordinates",
        "query": "91, 181",
        "latitude_bounds": [-90, 90],
        "longitude_bounds": [-180, 180],
    }

###############################################################################
@pytest.mark.asyncio
async def test_invalid_coordinates_in_user_text_override_context_target() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Go to 91, 181.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(query="Zurich", expected_location_type="city"),
        state,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_coordinates"
    assert result.data is not None
    assert result.data["query"] == "91, 181"

###############################################################################
@pytest.mark.asyncio
async def test_unresolved_target_id_is_resolved_as_initial_location_query() -> None:
    captured: list[tuple[str, str]] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            signal = signals[0]
            captured.append((signal.raw_value, signal.signal_type))
            return ResolvedLocation(
                label="Japan",
                latitude=36.2048,
                longitude=138.2529,
                source="geocoder",
            )

    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show me earthquakes around Japan.",
    )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(target_id="Japan", expected_location_type="country"),
        state,
    )

    assert result.status == "success"
    assert captured == [("Japan", "country")]
    assert state.location_refs["japan"].label == "Japan"

###############################################################################
@pytest.mark.asyncio
async def test_ambiguous_location_is_a_typed_semantic_outcome() -> None:

    ###############################################################################
    class AmbiguousResolver(LocationResolver):

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, _signals, _memory):  # noqa: ANN001
            return ClarificationRequest(
                question="Which Springfield do you mean?",
                reason="Multiple candidates matched.",
                missing_fields=["location"],
            )

    result = await LocationToolHandler(resolver=AmbiguousResolver()).resolve(
        ResolveLocationInput(query="Springfield"),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Show Springfield.",
        ),
    )

    assert result.status == "failed"
    assert result.semantic_outcome == "ambiguous"
    assert result.data == {
        "resolution_status": "ambiguous",
        "question": "Which Springfield do you mean?",
        "reason": "Multiple candidates matched.",
        "missing_fields": ["location"],
    }
    assert result.error is not None
    assert result.error.recovery == "request_user_input"

###############################################################################
@pytest.mark.asyncio
async def test_administrative_geometry_type_reaches_the_native_resolver() -> None:
    captured: list[str] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            captured.append(signals[0].signal_type)
            return ResolvedLocation(
                label="Vermont, United States",
                latitude=44.0,
                longitude=-72.7,
                source="geocoder",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(
            query="Vermont, United States",
            expected_location_type="administrative_geometry",
        ),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Show a map of Vermont, United States.",
        ),
    )

    assert result.status == "success"
    assert captured == ["administrative_geometry"]

###############################################################################
@pytest.mark.asyncio
async def test_explicit_coordinates_in_clarification_text_override_unresolved_name() -> None:
    captured: list[tuple[str, float | None, float | None, str]] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            signal = signals[0]
            captured.append(
                (signal.signal_type, signal.latitude, signal.longitude, signal.source)
            )
            return ResolvedLocation(
                label="45, -69",
                latitude=45.0,
                longitude=-69.0,
                source="text",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(
            query="Patagonia, Argentina",
            expected_location_type="region",
        ),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message=(
                "Use the broad region, centered approximately at 45.0, -69.0."
            ),
        ),
    )

    assert result.status == "success"
    assert captured == [("coordinates", 45.0, -69.0, "text")]

###############################################################################
@pytest.mark.asyncio
async def test_coordinate_text_supports_hemisphere_notation() -> None:

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            signal = signals[0]
            return ResolvedLocation(
                label=signal.raw_value,
                latitude=signal.latitude or 0.0,
                longitude=signal.longitude or 0.0,
                source="text",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(query="Patagonia, Argentina", expected_location_type="region"),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Center approximately at 45 degrees S, 69 degrees W.",
        ),
    )

    assert result.status == "success"
    assert result.data is not None
    assert result.data["coordinates"] == [-69.0, -45.0]

###############################################################################
def test_unknown_location_type_is_not_accepted_as_a_legacy_alias() -> None:
    with pytest.raises(ValidationError):
        ResolveLocationInput(
            query="Vermont, United States",
            expected_location_type="administrative_region",
        )
