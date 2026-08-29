from __future__ import annotations

from dataclasses import dataclass

from server.contracts.chat import ChatOperationResult
from server.domain.agent.decision import ResolvedLocation
from server.contracts.geospatial import MapSession, ViewportPolicy
from server.prompts.response import (
    VERIFIED_EVIDENCE_USER_TEMPLATE,
    build_grounded_response_system_prompt,
)
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer

###############################################################################
@dataclass
class _Settings:
    agent_model_provider: str = "test"
    agent_model_name: str = "test-model"

###############################################################################
class _SettingsRepo:

    # -------------------------------------------------------------------------
    def get_or_create(self) -> _Settings:
        return _Settings()

###############################################################################
class _Provider:

    # -------------------------------------------------------------------------
    def __init__(self, content: str = "**Map ready.**") -> None:
        self.content = content
        self.requests = []

    # -------------------------------------------------------------------------
    def structured_output(self, request, schema):  # noqa: ANN001
        self.requests.append(request)
        assert schema.__name__ == "GroundedSynthesisResult"
        return {
            "content": self.content,
            "used_evidence_keys": ["verified_outcome"],
            "warnings": [],
        }

###############################################################################
class _Factory:

    # -------------------------------------------------------------------------
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> _Provider:
        assert provider == "test"
        return self.provider

###############################################################################
def test_synthesizer_returns_grounded_markdown_and_bounded_evidence() -> None:
    provider = _Provider("**Rain layer ready.**\n\n- Current data")
    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(provider),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="direct_answer",
        status="success",
        message="Verified fallback.",
        warnings=["Current data only."],
        direct_result={"precipitation": 2.4},
    )

    result = synthesizer.synthesize(
        user_text="How much rain is there?",
        fallback_text="Verified fallback.",
        operation=operation,
        direct_result=operation.direct_result,
        task_status="completed",
    )

    assert result.startswith("**Rain layer ready.**")
    request_text = provider.requests[0].messages[1]["content"]
    assert "Verified fallback." in request_text
    assert "Current data only." in request_text
    assert "How much rain is there?" in request_text
    assert provider.requests[0].messages[0]["content"] == build_grounded_response_system_prompt()
    assert request_text.startswith(VERIFIED_EVIDENCE_USER_TEMPLATE.split("{", maxsplit=1)[0])

###############################################################################
def test_synthesizer_evidence_marks_metadata_only_overlays() -> None:
    provider = _Provider("Map context ready.")
    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(provider),  # type: ignore[arg-type]
        enabled=True,
    )
    map_session = MapSession(
        session_id="map-1",
        resolved_location=ResolvedLocation(
            label="Paris",
            latitude=48.8566,
            longitude=2.3522,
        ),
        basemap_id="osm_default",
        overlay_ids=["openmeteo_air_quality_forecast"],
        viewport=ViewportPolicy(
            center_latitude=48.8566,
            center_longitude=2.3522,
            radius_m=18000.0,
        ),
        overlays=[
            {
                "id": "openmeteo_air_quality_forecast",
                "label": "Open-Meteo Air Quality Forecast",
                "rendering_mode": "metadata-only",
                "source_protocol": "JSON time series",
            }
        ],
    )
    operation = ChatOperationResult(
        kind="map_session",
        status="success",
        message="Map ready.",
        map_session=map_session,
    )

    synthesizer.synthesize(
        user_text="Show air quality overlay for Paris.",
        fallback_text="Map ready.",
        operation=operation,
        map_session=map_session,
        task_status="completed",
    )

    system_text = provider.requests[0].messages[0]["content"]
    request_text = provider.requests[0].messages[1]["content"]
    assert '"rendered":false' in request_text
    assert '"status":"metadata_only"' in request_text
    assert "not a live rendered map layer" in system_text

###############################################################################
def test_synthesizer_falls_back_when_model_fails() -> None:

    ###############################################################################
    class _FailingProvider(_Provider):

        # -------------------------------------------------------------------------
        def structured_output(self, request, schema):  # noqa: ANN001
            _ = request, schema
            raise RuntimeError("offline")

    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(_FailingProvider()),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="clarification",
        status="partial",
        message="Choose a supported time basis.",
    )

    assert synthesizer.synthesize(
        user_text="October mean",
        fallback_text="Choose a supported time basis.",
        operation=operation,
    ) == "Choose a supported time basis."

###############################################################################
def test_synthesizer_does_not_rewrite_failed_or_policy_responses() -> None:
    provider = _Provider("This must not be used.")
    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(provider),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="error",
        status="failed",
        message="Credential rejected.",
    )

    result = synthesizer.synthesize(
        user_text="Run this",
        fallback_text="Credential rejected.",
        operation=operation,
    )

    assert result == "Credential rejected."
    assert provider.requests == []

###############################################################################
def test_synthesizer_falls_back_on_invalid_structured_output() -> None:

    ###############################################################################
    class _InvalidProvider(_Provider):

        # -------------------------------------------------------------------------
        def structured_output(self, request, schema):  # noqa: ANN001
            self.requests.append(request)
            return {"content": "", "used_evidence_keys": [], "warnings": []}

    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(_InvalidProvider()),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="direct_answer",
        status="success",
        message="Verified fallback.",
    )

    assert synthesizer.synthesize(
        user_text="Answer",
        fallback_text="Verified fallback.",
        operation=operation,
    ) == "Verified fallback."

###############################################################################
def test_synthesizer_falls_back_when_successful_overlay_is_called_failed() -> None:
    provider = _Provider("The overlay failed and is not available.")
    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(provider),  # type: ignore[arg-type]
        enabled=True,
    )
    map_session = MapSession(
        session_id="map-1",
        resolved_location=ResolvedLocation(label="Tokyo", latitude=35.6, longitude=139.7),
        basemap_id="osm_default",
        overlay_ids=["overpass_poi_amenities"],
        viewport=ViewportPolicy(center_latitude=35.6, center_longitude=139.7, radius_m=4000.0),
        overlays=[{"id": "overpass_poi_amenities", "rendering_mode": "clustered-points"}],
    )
    operation = ChatOperationResult(kind="map_session", status="success", message="Verified.", map_session=map_session)

    assert synthesizer.synthesize(
        user_text="Show rail stations in Tokyo.",
        fallback_text="Map ready with the verified POI overlay.",
        operation=operation,
        map_session=map_session,
    ) == "Map ready with the verified POI overlay."
