from __future__ import annotations

import asyncio

from server.domain.agent.tools import AgentToolCall
from server.services.agent.tool_executor import AgentExecutionContext, AgentToolExecutor


class _Registry:
    def get_capability(self, capability_id: str):
        return {"id": capability_id, "name": "Rain", "provider": "rainviewer", "default_opacity": 0.5}

    def list_overlays(self):
        return [{"id": "rain_layer"}]

    def list_cameras(self):
        return []

    def list_transit(self):
        return []


def test_unknown_tool_returns_error() -> None:
    async def _run() -> None:
        result = await AgentToolExecutor(capability_registry=_Registry()).execute(
            AgentToolCall(name="missing", arguments={}),
            AgentExecutionContext(),
        )
        assert result.error

    asyncio.run(_run())


def test_overlay_tool_resolves_through_registry() -> None:
    async def _run() -> None:
        result = await AgentToolExecutor(capability_registry=_Registry()).execute(
            AgentToolCall(name="overlay__rain_layer", arguments={"visible": True}),
            AgentExecutionContext(),
        )
        assert result.error is None
        assert result.result["overlay_id"] == "rain_layer"
        assert result.result["type"] == "load_overlay"

    asyncio.run(_run())


def test_map_payload_contains_frontend_actionable_fields() -> None:
    async def _run() -> None:
        result = await AgentToolExecutor(capability_registry=_Registry()).execute(
            AgentToolCall(name="load_map_overlay", arguments={"overlay_id": "rain_layer"}),
            AgentExecutionContext(),
        )
        assert {"overlay_id", "layer_id", "visibility", "opacity", "legend", "source_attribution"}.issubset(result.result)

    asyncio.run(_run())
