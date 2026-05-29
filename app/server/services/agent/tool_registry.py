from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.llm.types import LLMToolDefinition
from server.services.agent.tool_handlers import air_quality, coordinates, poi, weather
from server.services.geospatial.runtime_registry import RuntimeRegistry

ToolHandler = Callable[[ExecutionPlan, ResolvedLocation], Awaitable[dict[str, object]]]
NativeToolHandler = Callable[[dict[str, Any], Any], Awaitable[Any]]


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str


@dataclass(frozen=True)
class ToolExecutionEnvelope:
    ok: bool
    data: Any | None = None
    error: ToolError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": None
            if self.error is None
            else {"code": self.error.code, "message": self.error.message},
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RegisteredNativeTool:
    definition: LLMToolDefinition
    handler: NativeToolHandler


class ToolRegistry:
    def __init__(self, *, runtime_registry: RuntimeRegistry | None = None) -> None:
        self.runtime_registry = runtime_registry or RuntimeRegistry()
        self._handlers: dict[str, ToolHandler] = {}
        self._native_tools: dict[str, RegisteredNativeTool] = {}

    def register_native_tool(
        self,
        definition: LLMToolDefinition,
        handler: NativeToolHandler,
    ) -> None:
        self._native_tools[definition.name] = RegisteredNativeTool(
            definition=definition,
            handler=handler,
        )

    def list_native_tools(self) -> list[LLMToolDefinition]:
        return [item.definition for item in self._native_tools.values()]

    def has_native_tool(self, name: str) -> bool:
        return name in self._native_tools

    async def execute_native_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Any,
    ) -> ToolExecutionEnvelope:
        registered = self._native_tools.get(name)
        if registered is None:
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(
                    code="unknown_tool",
                    message=f"No native tool registered for '{name}'.",
                ),
            )
        validation_error = self._validate_arguments(
            registered.definition.parameters_json_schema,
            arguments,
        )
        if validation_error is not None:
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(code="invalid_arguments", message=validation_error),
            )
        try:
            result = await registered.handler(arguments, context)
        except Exception as exc:
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(code="tool_execution_error", message=str(exc)),
            )
        return ToolExecutionEnvelope(ok=True, data=result)

    @classmethod
    def _validate_arguments(
        cls,
        schema: dict[str, Any],
        arguments: dict[str, Any],
    ) -> str | None:
        if not isinstance(arguments, dict):
            return "Tool arguments must be an object."
        required = schema.get("required")
        if isinstance(required, list):
            for field_name in required:
                if isinstance(field_name, str) and field_name not in arguments:
                    return f"Missing required argument '{field_name}'."
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return None
        for field_name, value in arguments.items():
            field_schema = properties.get(field_name)
            if not isinstance(field_schema, dict):
                continue
            expected_type = field_schema.get("type")
            if expected_type and not cls._matches_json_type(value, expected_type):
                return f"Argument '{field_name}' must be {expected_type}."
        return None

    @staticmethod
    def _matches_json_type(value: Any, expected_type: Any) -> bool:
        expected = {expected_type} if isinstance(expected_type, str) else set(expected_type)
        return (
            ("string" in expected and isinstance(value, str))
            or ("integer" in expected and isinstance(value, int) and not isinstance(value, bool))
            or ("number" in expected and isinstance(value, (int, float)) and not isinstance(value, bool))
            or ("boolean" in expected and isinstance(value, bool))
            or ("object" in expected and isinstance(value, dict))
            or ("array" in expected and isinstance(value, list))
            or ("null" in expected and value is None)
        )

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
