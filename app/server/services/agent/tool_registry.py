from __future__ import annotations

from collections.abc import Awaitable, Callable

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.agent.tool_handlers import air_quality, coordinates, poi, weather
from server.services.geospatial.runtime_registry import RuntimeRegistry

ToolHandler = Callable[[ExecutionPlan, ResolvedLocation], Awaitable[dict[str, object]]]


class ToolRegistry:
    def __init__(self, *, runtime_registry: RuntimeRegistry | None = None) -> None:
        self.runtime_registry = runtime_registry or RuntimeRegistry()
        self._handlers: dict[str, ToolHandler] = {}

    def load_tool_bindings(self) -> dict[str, ToolHandler]:
        self.runtime_registry.build_snapshot()
        handler_lookup: dict[str, ToolHandler] = {
            "coordinates": coordinates.execute,
            "weather": weather.execute,
            "air_quality": air_quality.execute,
            "poi": poi.execute,
        }
        bindings: dict[str, ToolHandler] = {}
        for capability_id, profile in self.runtime_registry._ensure().profiles.items():
            handler_name = str(profile.get("handler_name") or "").strip()
            if not handler_name:
                continue
            handler = handler_lookup.get(handler_name)
            if handler is None:
                continue
            bindings[capability_id] = handler
        self._handlers = bindings
        return bindings

    def get_handler(self, tool_id: str) -> ToolHandler | None:
        if not self._handlers:
            self.load_tool_bindings()
        return self._handlers.get(tool_id)

    async def execute(
        self,
        tool_id: str,
        plan: ExecutionPlan,
        location: ResolvedLocation,
    ) -> dict[str, object]:
        handler = self.get_handler(tool_id)
        if handler is None:
            return {
                "tool": tool_id,
                "error": f"No tool handler registered for '{tool_id}'.",
            }
        payload = await handler(plan, location)
        return {
            "tool_id": tool_id,
            "plan_state": plan.state,
            "location": {
                "label": location.label,
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
            "result": payload,
        }
