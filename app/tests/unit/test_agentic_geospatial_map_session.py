from __future__ import annotations

import asyncio
import json
import threading
from typing import TypeVar

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.contracts.geospatial import ProviderLayerSelection
from server.services.geospatial.providers.base import ProviderRateLimitError
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

T = TypeVar("T")


###############################################################################
def _run_async(awaitable) -> T:  # type: ignore[no-untyped-def]
    result: dict[str, T] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # noqa: BLE001
            error["value"] = exc

    thread = threading.Thread(target=_runner, name="test-async-runner")
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result["value"]


###############################################################################
def test_agentic_geospatial_selected_capabilities_flow_into_map_session() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="traffic",
        basemap_id="osm_default",
        overlay_ids=["tomtom_traffic_flow", "windy_webcams"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))

    assert session.overlay_ids == ["tomtom_traffic_flow", "windy_webcams"]
    assert [overlay["id"] for overlay in session.overlays] == [
        "tomtom_traffic_flow",
        "windy_webcams",
    ]
    assert session.center == {"latitude": 41.9, "longitude": 12.5}
    assert session.requested_overlay_ids == ["tomtom_traffic_flow", "windy_webcams"]
    assert session.rendered_overlay_ids == ["tomtom_traffic_flow", "windy_webcams"]
    assert session.failed_overlays == []


###############################################################################
def test_agentic_geospatial_map_session_separates_failed_overlay_ids() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="traffic",
        basemap_id="osm_default",
        overlay_ids=["tomtom_traffic_flow", "missing_overlay"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))

    assert session.requested_overlay_ids == ["tomtom_traffic_flow", "missing_overlay"]
    assert session.overlay_ids == ["tomtom_traffic_flow"]
    assert session.rendered_overlay_ids == ["tomtom_traffic_flow"]
    assert session.failed_overlays == [
        {"id": "missing_overlay", "reason": "not available in the capability catalog"}
    ]


###############################################################################
class _ProviderLayerRenderService:
    # -------------------------------------------------------------------------
    async def build_basemap_descriptor(self, basemap_id: str) -> dict[str, object]:
        return {"id": basemap_id, "tile_url": "https://tiles.example/{z}/{x}/{y}.png"}

    # -------------------------------------------------------------------------
    async def build_overlay_descriptor(self, overlay_id: str, *, request):  # noqa: ANN001
        _ = overlay_id, request
        return None

    # -------------------------------------------------------------------------
    async def build_provider_layer_overlay(
        self,
        *,
        provider_id: str,
        layer_id: str,
        request,  # noqa: ANN001
        refresh: bool = False,
    ) -> tuple[dict[str, object], list[str]]:
        _ = request, refresh
        return (
            {
                "id": f"{provider_id}:{layer_id}",
                "label": "GIBS True Color",
                "provider": provider_id,
                "type": "raster-overlay",
                "rendering_mode": "wmts",
                "tile_url_template": "https://gibs.example/{z}/{x}/{y}.png",
                "render": {
                    "provider": provider_id,
                    "layer_id": layer_id,
                    "rendering_mode": "wmts",
                    "source_protocol": "wmts",
                    "tile_url_template": "https://gibs.example/{z}/{x}/{y}.png",
                },
            },
            [],
        )


###############################################################################
class _FailedProviderLayerRenderService(_ProviderLayerRenderService):
    # -------------------------------------------------------------------------
    async def build_provider_layer_overlay(
        self,
        *,
        provider_id: str,
        layer_id: str,
        request,  # noqa: ANN001
        refresh: bool = False,
    ) -> tuple[dict[str, object], list[str]]:
        _ = provider_id, layer_id, request, refresh
        raise ProviderRateLimitError("provider rate limit reached")


###############################################################################
def test_agentic_geospatial_provider_layer_selection_flows_into_map_session() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="imagery",
        basemap_id="osm_default",
        overlay_ids=[],
    )
    request = RequestBuilder().build_location_search_request(
        plan,
        location,
        provider_layer_selections=[
            ProviderLayerSelection(
                provider_id="gibs",
                layer_id="MODIS_Terra_CorrectedReflectance_TrueColor",
            )
        ],
    )

    session = _run_async(
        LocationSearchOrchestrator(
            render_descriptor_service=_ProviderLayerRenderService(),  # type: ignore[arg-type]
        ).execute(request)
    )

    assert session.requested_overlay_ids == [
        "gibs:MODIS_Terra_CorrectedReflectance_TrueColor"
    ]
    assert session.overlay_ids == ["gibs:MODIS_Terra_CorrectedReflectance_TrueColor"]
    assert (
        session.overlays[0]["tile_url_template"]
        == "https://gibs.example/{z}/{x}/{y}.png"
    )
    assert session.failed_overlays == []


###############################################################################
def test_agentic_geospatial_provider_layer_failure_preserves_error_code() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="imagery",
        basemap_id="osm_default",
        overlay_ids=[],
    )
    request = RequestBuilder().build_location_search_request(
        plan,
        location,
        provider_layer_selections=[
            ProviderLayerSelection(provider_id="gibs", layer_id="broken-layer")
        ],
    )

    session = _run_async(
        LocationSearchOrchestrator(
            render_descriptor_service=_FailedProviderLayerRenderService(),  # type: ignore[arg-type]
        ).execute(request)
    )

    assert session.overlay_ids == []
    assert session.failed_overlays == [
        {
            "id": "gibs:broken-layer",
            "reason": "provider rate limit reached",
            "code": "rate_limited",
        }
    ]


###############################################################################
def test_agentic_geospatial_map_session_uses_public_openfreemap_basemap() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="traffic",
        basemap_id="openfreemap_liberty",
        overlay_ids=["tomtom_traffic_flow"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))

    assert session.basemap_id == "openfreemap_liberty"
    assert not any(
        "provider API key is required" in item for item in session.compliance_warnings
    )


###############################################################################
def test_agentic_geospatial_map_session_never_serializes_provider_api_keys(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TOMTOM_API_KEY", "tomtom-secret-forbidden")
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="traffic",
        basemap_id="osm_default",
        overlay_ids=["tomtom_traffic_flow"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))

    serialized = json.dumps(session.model_dump(mode="json"))
    assert "tomtom-secret-forbidden" not in serialized
    assert "api_key=" not in serialized
    assert "/api/geospatial/tiles/tomtom_traffic_flow/" in serialized


###############################################################################
def test_agentic_geospatial_wms_and_wmts_descriptors_include_backend_render_templates() -> (
    None
):
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="thematic_layers",
        basemap_id="osm_default",
        overlay_ids=["eea_noise_2019", "esa_worldcover"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))
    overlays = {overlay["id"]: overlay for overlay in session.overlays}

    eea = overlays["eea_noise_2019"]
    esa = overlays["esa_worldcover"]

    assert eea["rendering_mode"] == "wms"
    assert "service=WMS" in eea["tile_url_template"]
    assert "request=GetMap" in eea["tile_url_template"]
    assert "version=1.1.1" in eea["tile_url_template"]
    assert "bbox={bbox-epsg-3857}" in eea["tile_url_template"]

    assert esa["rendering_mode"] == "wmts"
    assert "service=WMTS" in esa["tile_url_template"]
    assert "request=GetTile" in esa["tile_url_template"]
    assert "tilematrixset=EPSG:3857" in esa["tile_url_template"]
    assert "tilematrix=EPSG:3857:{z}" in esa["tile_url_template"]


###############################################################################
def test_agentic_geospatial_metadata_only_descriptors_stay_non_renderable() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        confidence=1.0,
    )
    plan = ExecutionPlan(
        state="map_search",
        action_id="regional_demographics",
        basemap_id="osm_default",
        overlay_ids=["eurostat_regional_demographics"],
    )
    request = RequestBuilder().build_location_search_request(plan, location)

    session = _run_async(LocationSearchOrchestrator().execute(request))
    overlay = session.overlays[0]

    assert overlay["id"] == "eurostat_regional_demographics"
    assert overlay["rendering_mode"] == "metadata-only"
    assert overlay["type"] == "time-series-insight"
    assert "tile_url_template" not in overlay
