from __future__ import annotations

import json
from typing import Any

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.evidence import AgentEvidenceSummary
from server.services.agent.tool_definitions import InspectEvidenceInput
from server.services.agent.tool_handlers.evidence import EvidenceToolHandler
from server.services.geospatial.api_service import GeospatialSampleUnavailableError

LEGEND = {
    "kind": "categorical",
    "title": "Land cover",
    "units": None,
    "entries": [{"color": "#00ff00", "label": "Forest"}],
}

###############################################################################
class _Evidence:

    # -------------------------------------------------------------------------
    def __init__(self, kind: str, payload: dict[str, Any]) -> None:
        self.item = (
            AgentEvidenceSummary(
                evidence_id="raster-1",
                kind=kind,  # type: ignore[arg-type]
                media_type="application/json",
                status="available",
                provenance={"capability_id": "fixture_land_cover"},
            ),
            json.dumps(payload).encode(),
        )

    # -------------------------------------------------------------------------
    def get_payload(self, evidence_id: str, *, conversation_id: str | None = None):  # noqa: ANN201, ARG002
        return self.item

###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="what land cover is at these points",
        evidence_refs=["raster-1"],
    )

###############################################################################
def _request(*points: tuple[float, float]) -> InspectEvidenceInput:
    return InspectEvidenceInput.model_validate(
        {
            "evidence_ref": "raster-1",
            "view": "values_at",
            "points": [{"lon": lon, "lat": lat} for lon, lat in points],
        }
    )

###############################################################################
async def test_values_at_samples_each_point_with_descriptor_legend_and_time() -> None:
    calls: list[tuple[Any, ...]] = []

    async def sampler(capability_id: str, lon: float, lat: float, z: int, time: str | None, *, legend: Any) -> dict[str, Any]:
        calls.append((capability_id, z, time, legend))
        sample = {"value": None, "label": "Forest", "units": None, "kind": "categorical", "matched_color": "#00ff00"}
        return {"z": z, "time": time, "legend_title": "Land cover", "units": None, "kind": "categorical",
                "sample": sample if lon > 0 else None}

    handler = EvidenceToolHandler(
        repository=_Evidence("raster_descriptor", {"render": {"time": "2021-01-01"}, "legend": LEGEND}),  # type: ignore[arg-type]
        raster_sampler=sampler,
    )

    result = await handler.inspect(_request((10.0, 45.0), (-10.0, 45.0)), _state())

    assert result.status == "success"
    assert calls[0] == ("fixture_land_cover", 8, "2021-01-01", LEGEND)
    assert result.data["result"]["points"] == [  # type: ignore[index]
        {"lon": 10.0, "lat": 45.0, "value": None, "label": "Forest"},
        {"lon": -10.0, "lat": 45.0, "value": None, "label": None, "no_data": True},
    ]

###############################################################################
async def test_values_at_reports_layer_without_legend_and_non_raster_evidence() -> None:
    async def sampler(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise GeospatialSampleUnavailableError("Capability 'fixture_land_cover' has no colour legend to read values from.")

    no_legend = await EvidenceToolHandler(
        repository=_Evidence("raster_descriptor", {"render": {}}),  # type: ignore[arg-type]
        raster_sampler=sampler,
    ).inspect(_request((10.0, 45.0)), _state())
    records = await EvidenceToolHandler(
        repository=_Evidence("vector", {"features": []}),  # type: ignore[arg-type]
        raster_sampler=sampler,
    ).inspect(_request((10.0, 45.0)), _state())

    assert no_legend.status == "failed" and no_legend.error is not None
    assert no_legend.error.code == "no_legend"
    assert records.status == "failed" and records.error is not None
    assert records.error.code == "unsupported_view"
