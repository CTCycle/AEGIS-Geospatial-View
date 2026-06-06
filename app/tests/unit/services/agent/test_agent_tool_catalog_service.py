from __future__ import annotations

import asyncio
from typing import Any

from server.domain.agent.decision import ResolvedLocation
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TurnParseResult,
)
from server.domain.geographics import MapSession
from server.services.agent.agent_tool_catalog_service import (
    AgentToolCatalogService,
    CapabilityCatalogFilter,
)
from server.services.agent.native_tool_loop import AgentExecutionContext
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.search.request_builder import RequestBuilder


class _CapabilityRegistry:
    def __init__(self) -> None:
        self.load_calls = 0
        self.capabilities = [
            {
                "id": "weather_overlay",
                "name": "Weather Overlay",
                "description": "Weather map overlay",
                "provider": "test",
                "type": "overlay",
                "capabilityKind": "vector-overlay",
                "metadata": {
                    "geometry_type": "point",
                    "argument_schema": {
                        "type": "object",
                        "properties": {
                            "bbox": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 4,
                                "maxItems": 4,
                            }
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "id": "coordinates_tool",
                "name": "Coordinates Tool",
                "description": "Coordinates direct tool",
                "provider": "test",
                "type": "direct-tool",
                "capabilityKind": "analysis-tool",
                "metadata": {
                    "geometry_type": "not-applicable",
                    "argument_schema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                        },
                        "required": ["location"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "id": "tomtom_traffic_flow",
                "name": "TomTom Traffic Flow",
                "description": "Credentialed traffic overlay",
                "provider": "tomtom",
                "type": "tile",
                "capabilityKind": "raster-overlay",
                "metadata": {
                    "geometry_type": "raster-grid",
                    "argument_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                "auth": {"required": True, "providerKey": "tomtom"},
            },
        ]

    def load_capabilities(self):
        self.load_calls += 1
        return type(
            "Snapshot",
            (),
            {
                "basemaps": [],
                "overlays": [self.capabilities[0], self.capabilities[2]],
                "cameras": [],
                "transit": [],
                "tools": [self.capabilities[1]],
            },
        )()

    def get_capability(self, capability_id: str):
        return next((item for item in self.capabilities if item["id"] == capability_id), None)


class _RuntimeRegistry:
    def is_enabled(self, capability_id: str) -> bool:
        return capability_id != "disabled_capability"

    def provider_health(self, capability_id: str) -> str:
        if capability_id == "tomtom_traffic_flow":
            return "missing_credentials"
        return "healthy"

    def supports_mode(self, capability_id: str, mode: str) -> bool:
        supported = {
            "weather_overlay": {"map"},
            "coordinates_tool": {"direct_text"},
            "tomtom_traffic_flow": {"map"},
        }
        return mode in supported.get(capability_id, set())


class _LocationResolver:
    async def resolve_location_signals(self, location_signals, memory_snapshot):  # noqa: ANN001
        signal = location_signals[0] if location_signals else None
        if signal is None:
            active = memory_snapshot.get("active_location") or {}
            return ResolvedLocation(
                label=str(active.get("label") or "Rome"),
                latitude=float(active.get("latitude") or 41.9028),
                longitude=float(active.get("longitude") or 12.4964),
                source="memory",
                confidence=0.9,
            )
        return ResolvedLocation(
            label=signal.normalized_value or signal.raw_value,
            latitude=float(signal.latitude or 41.9028),
            longitude=float(signal.longitude or 12.4964),
            source=signal.source,
            confidence=signal.confidence or 0.9,
        )


class _SearchOrchestrator:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def execute(self, payload):  # noqa: ANN001
        self.requests.append(payload)
        return MapSession(
            session_id="map-1",
            resolved_location=payload.resolved_location,
            basemap_id=payload.basemap_id,
            overlay_ids=payload.overlay_ids,
            viewport=payload.viewport,
            basemap={"id": payload.basemap_id, "label": payload.basemap_id},
            overlays=[{"id": overlay_id, "label": overlay_id} for overlay_id in payload.overlay_ids],
            payload={"action_id": payload.action_id},
            center={
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            bounds=[12.0, 41.0, 13.0, 42.0],
        )


class _ToolRegistry:
    async def execute(self, tool_id, plan, location):  # noqa: ANN001
        return {
            "tool_id": tool_id,
            "plan_state": plan.state,
            "location": {"label": location.label},
            "result": {"coordinates": {"latitude": location.latitude, "longitude": location.longitude}},
        }

    def get_handler(self, tool_id: str):  # noqa: ARG002
        return object()


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        parsed_request=TurnParseResult(
            user_text="Show Rome weather",
            conversation_context=ConversationContextSnapshot(
                memory_snapshot={
                    "active_location": {
                        "label": "Rome",
                        "latitude": 41.9028,
                        "longitude": 12.4964,
                    }
                }
            ).model_dump(mode="json"),
            task_class="map_search",
            location_signals=[
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome",
                    normalized_value="Rome",
                    latitude=41.9028,
                    longitude=12.4964,
                    confidence=0.9,
                )
            ],
            normalized_action=NormalizedAction(
                action_id="weather",
                action_label="Weather",
                requires_location=True,
            ),
            parser_confidence=0.9,
        ).model_dump(mode="json"),
        map_state={
            "active_location": {
                "label": "Rome",
                "latitude": 41.9028,
                "longitude": 12.4964,
            }
        },
    )


def _direct_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        parsed_request=TurnParseResult(
            user_text="What are the coordinates for Rome?",
            conversation_context=ConversationContextSnapshot(
                memory_snapshot={
                    "active_location": {
                        "label": "Rome",
                        "latitude": 41.9028,
                        "longitude": 12.4964,
                    }
                }
            ).model_dump(mode="json"),
            task_class="direct_query",
            location_signals=[
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome",
                    normalized_value="Rome",
                    latitude=41.9028,
                    longitude=12.4964,
                    confidence=0.9,
                )
            ],
            normalized_action=NormalizedAction(
                action_id="location_to_coordinates",
                action_label="Location To Coordinates",
                requires_location=True,
            ),
            parser_confidence=0.9,
        ).model_dump(mode="json"),
        map_state={
            "active_location": {
                "label": "Rome",
                "latitude": 41.9028,
                "longitude": 12.4964,
            }
        },
    )


def _service() -> AgentToolCatalogService:
    runtime_registry = _RuntimeRegistry()
    policy_engine = PolicyEngine(
        location_resolver=_LocationResolver(),  # type: ignore[arg-type]
        capability_registry=_CapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=runtime_registry,  # type: ignore[arg-type]
    )
    return AgentToolCatalogService(
        capability_registry=_CapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=runtime_registry,  # type: ignore[arg-type]
        search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
        request_builder=RequestBuilder(),
        location_resolver=_LocationResolver(),  # type: ignore[arg-type]
        tool_registry=_ToolRegistry(),  # type: ignore[arg-type]
        policy_engine=policy_engine,
    )


def test_catalog_builds_stable_native_tools() -> None:
    service = _service()
    names = [tool.name for tool in service.build_native_tools()]
    assert names == [
        "list_geospatial_capabilities",
        "describe_geospatial_capability",
        "execute_geospatial_capability",
    ]


def test_catalog_pagination_is_deterministic() -> None:
    service = _service()
    first = service.list_geospatial_capabilities(CapabilityCatalogFilter(limit=1))
    second = service.list_geospatial_capabilities(CapabilityCatalogFilter(limit=1, cursor=first["next_cursor"]))
    assert first["items"][0]["id"] == "coordinates_tool"
    assert second["items"][0]["id"] == "tomtom_traffic_flow"


def test_capability_description_includes_executable_schema() -> None:
    service = _service()
    descriptor = service.describe_geospatial_capability("coordinates_tool")
    assert descriptor["argument_schema"]["required"] == ["location"]


def test_execute_rejects_invalid_nested_arguments() -> None:
    result = asyncio.run(
        _service().execute_geospatial_capability(
            "weather_overlay",
            {"bbox": [12.0, "bad", 13.0, 42.0, 9.0]},
            context=_context(),
        )
    )

    assert result["ok"] is False
    assert result["operation"] == "invalid_arguments"
    assert result["error"] is not None
    assert "bbox" in result["error"]["message"]


def test_execute_map_capability_returns_real_map_session() -> None:
    result = asyncio.run(
        _service().execute_geospatial_capability(
            "weather_overlay",
            {},
            context=_context(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "map_session_created"
    assert result["map_session"] is not None
    assert result["map_session"]["resolved_location"]["label"] == "Rome"


def test_execute_direct_capability_returns_direct_result() -> None:
    result = asyncio.run(
        _service().execute_geospatial_capability(
            "coordinates_tool",
            {"location": "Rome"},
            context=_direct_context(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "direct_result_created"
    assert result["direct_result"] is not None
    assert result["direct_result"]["tool_id"] == "coordinates_tool"


def test_execute_returns_missing_credentials_without_fake_success() -> None:
    result = asyncio.run(
        _service().execute_geospatial_capability(
            "tomtom_traffic_flow",
            {},
            context=_context(),
        )
    )

    assert result["ok"] is False
    assert result["operation"] == "missing_credentials"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_credentials"


def test_execute_rejects_direct_only_capability_for_map_request() -> None:
    result = asyncio.run(
        _service().execute_geospatial_capability(
            "coordinates_tool",
            {"location": "Rome"},
            context=_context(),
        )
    )

    assert result["ok"] is False
    assert result["operation"] == "unsupported_capability"
    assert result["error"] is not None
    assert result["error"]["code"] == "unsupported_capability"


def test_catalog_tools_register_with_tool_registry() -> None:
    registry = ToolRegistry()
    _service().register_with(registry)
    assert registry.has_native_tool("list_geospatial_capabilities")
    assert len(registry.list_native_tools()) == 3
