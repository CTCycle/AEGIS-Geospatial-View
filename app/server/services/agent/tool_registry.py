from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.domain.agent.tools import (
    RegisteredNativeTool,
    ToolError,
    ToolExecutionEnvelope,
)
from server.services.agent.tool_handlers import air_quality, coordinates, poi, weather
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition

ToolHandler = Callable[[ExecutionPlan, ResolvedLocation], Awaitable[dict[str, object]]]
NativeToolHandler = Callable[[dict[str, Any], Any], Awaitable[Any]]

###############################################################################
class ToolRegistry:

    # -------------------------------------------------------------------------
    def __init__(self, *, runtime_registry: RuntimeRegistry) -> None:
        self.runtime_registry = runtime_registry
        self._handlers: dict[str, ToolHandler] = {}
        self._native_tools: dict[str, RegisteredNativeTool] = {}

    # -------------------------------------------------------------------------
    def register_native_tool(
        self,
        definition: LLMToolDefinition,
        handler: NativeToolHandler,
    ) -> None:
        self._native_tools[definition.name] = RegisteredNativeTool(
            definition=definition,
            handler=handler,
        )

    # -------------------------------------------------------------------------
    def list_native_tools(self) -> list[LLMToolDefinition]:
        return [item.definition for item in self._native_tools.values()]

    # -------------------------------------------------------------------------
    def has_native_tool(self, name: str) -> bool:
        return name in self._native_tools

    # -------------------------------------------------------------------------
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
        if validation_error is None:
            validation_error = self._validate_domain_arguments(arguments)
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

    # -------------------------------------------------------------------------
    @classmethod
    def _validate_arguments(
        cls,
        schema: dict[str, Any],
        arguments: dict[str, Any],
    ) -> str | None:
        if not is_json_object(arguments):
            return "Tool arguments must be an object."
        return cls._validate_schema_node(schema, arguments, path="")

    # -------------------------------------------------------------------------
    @classmethod
    def _validate_domain_arguments(cls, arguments: dict[str, Any]) -> str | None:
        """Validate cross-field geospatial invariants before a handler runs."""

        def walk(value: Any, path: str = "") -> str | None:
            if is_json_object(value):
                for key, child in value.items():
                    child_path = cls._child_path(path, key)
                    key_lower = key.lower()
                    if key_lower in {"latitude", "lat"} and isinstance(child, (int, float)):
                        if not -90 <= child <= 90:
                            return f"Argument '{child_path}' must be between -90 and 90."
                    if key_lower in {"longitude", "lon", "lng"} and isinstance(child, (int, float)):
                        if not -180 <= child <= 180:
                            return f"Argument '{child_path}' must be between -180 and 180."
                    if key_lower in {"radius", "radius_m", "radius_km"} and isinstance(child, (int, float)):
                        if child <= 0:
                            return f"Argument '{child_path}' must be greater than zero."
                    nested_error = walk(child, child_path)
                    if nested_error:
                        return nested_error
                bbox = value.get("bbox")
                if is_json_array(bbox) and len(bbox) == 4 and all(isinstance(item, (int, float)) for item in bbox):
                    west, south, east, north = bbox
                    if west < -180 or east > 180 or south < -90 or north > 90:
                        return "Argument 'bbox' contains coordinates outside supported ranges."
                    if west > east or south > north:
                        return "Argument 'bbox' must be ordered west,south,east,north."
                for start_key, end_key in (("start", "end"), ("start_time", "end_time"), ("from", "to")):
                    start, end = value.get(start_key), value.get(end_key)
                    if isinstance(start, str) and isinstance(end, str):
                        try:
                            if datetime.fromisoformat(start.replace("Z", "+00:00")) > datetime.fromisoformat(end.replace("Z", "+00:00")):
                                return f"Arguments '{start_key}' and '{end_key}' are in reverse order."
                        except ValueError:
                            return f"Argument '{start_key}' or '{end_key}' is not a valid ISO-8601 timestamp."
            if is_json_array(value):
                for index, child in enumerate(value):
                    nested_error = walk(child, cls._child_path(path, str(index)))
                    if nested_error:
                        return nested_error
            return None

        return walk(arguments)

    # -------------------------------------------------------------------------
    @classmethod
    def _validate_schema_node(
        cls,
        schema: dict[str, Any],
        value: Any,
        *,
        path: str,
    ) -> str | None:
        expected_type = schema.get("type")
        if expected_type and not cls._matches_json_type(value, expected_type):
            return f"{cls._label_for_path(path)} must be {cls._format_expected_type(expected_type)}."

        enum_values = schema.get("enum")
        if is_json_array(enum_values) and value not in enum_values:
            return f"{cls._label_for_path(path)} must be one of {enum_values!r}."

        if is_json_object(value):
            object_error = cls._validate_object_schema(schema, value, path=path)
            if object_error is not None:
                return object_error
        if is_json_array(value):
            array_error = cls._validate_array_schema(schema, value, path=path)
            if array_error is not None:
                return array_error

        numeric_error = cls._validate_numeric_schema(schema, value, path=path)
        if numeric_error is not None:
            return numeric_error
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _validate_object_schema(
        cls,
        schema: dict[str, Any],
        value: dict[str, Any],
        *,
        path: str,
    ) -> str | None:
        required = schema.get("required")
        if is_json_array(required):
            for field_name in required:
                if isinstance(field_name, str) and field_name not in value:
                    missing_path = cls._child_path(path, field_name)
                    return f"Missing required argument '{missing_path}'."

        properties = schema.get("properties")
        if not is_json_object(properties):
            return None

        if schema.get("additionalProperties") is False:
            for field_name in value:
                if field_name not in properties:
                    unknown_path = cls._child_path(path, field_name)
                    return f"Unknown argument '{unknown_path}'."

        for field_name, field_value in value.items():
            field_schema = properties.get(field_name)
            if not is_json_object(field_schema):
                continue
            field_path = cls._child_path(path, field_name)
            field_error = cls._validate_schema_node(field_schema, field_value, path=field_path)
            if field_error is not None:
                return field_error
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _validate_array_schema(
        cls,
        schema: dict[str, Any],
        value: list[Any],
        *,
        path: str,
    ) -> str | None:
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            return f"{cls._label_for_path(path)} must contain at least {min_items} items."
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            return f"{cls._label_for_path(path)} must contain at most {max_items} items."

        item_schema = schema.get("items")
        if not is_json_object(item_schema):
            return None
        for index, item in enumerate(value):
            item_path = cls._child_path(path, str(index))
            item_error = cls._validate_schema_node(item_schema, item, path=item_path)
            if item_error is not None:
                return item_error
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _validate_numeric_schema(
        cls,
        schema: dict[str, Any],
        value: Any,
        *,
        path: str,
    ) -> str | None:
        if not isinstance(value, int | float) or isinstance(value, bool):
            return None
        minimum = schema.get("minimum")
        if isinstance(minimum, int | float) and value < minimum:
            return f"{cls._label_for_path(path)} must be >= {minimum}."
        maximum = schema.get("maximum")
        if isinstance(maximum, int | float) and value > maximum:
            return f"{cls._label_for_path(path)} must be <= {maximum}."
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _child_path(path: str, child: str) -> str:
        if not path:
            return child
        if child.isdigit():
            return f"{path}[{child}]"
        return f"{path}.{child}"

    # -------------------------------------------------------------------------
    @staticmethod
    def _label_for_path(path: str) -> str:
        return f"Argument '{path}'" if path else "Tool arguments"

    # -------------------------------------------------------------------------
    @staticmethod
    def _format_expected_type(expected_type: Any) -> str:
        if isinstance(expected_type, str):
            return expected_type
        if is_json_array(expected_type):
            return " or ".join(str(item) for item in expected_type)
        return str(expected_type)

    # -------------------------------------------------------------------------
    @staticmethod
    def _matches_json_type(value: Any, expected_type: Any) -> bool:
        expected = {expected_type} if isinstance(expected_type, str) else set(expected_type)
        return (
            ("string" in expected and isinstance(value, str))
            or ("integer" in expected and isinstance(value, int) and not isinstance(value, bool))
            or ("number" in expected and isinstance(value, (int, float)) and not isinstance(value, bool))
            or ("boolean" in expected and isinstance(value, bool))
            or ("object" in expected and is_json_object(value))
            or ("array" in expected and is_json_array(value))
            or ("null" in expected and value is None)
        )

    # -------------------------------------------------------------------------
    def load_tool_bindings(self) -> dict[str, ToolHandler]:
        self.runtime_registry.build_snapshot()
        handler_lookup: dict[str, ToolHandler] = {
            "coordinates": coordinates.execute,
            "weather": weather.execute,
            "air_quality": air_quality.execute,
            "poi": poi.execute,
        }
        bindings: dict[str, ToolHandler] = {}
        for capability_id, profile in self.runtime_registry._ensure().profiles.items():  # pyright: ignore[reportPrivateUsage]
            handler_name = str(profile.get("handler_name") or "").strip()
            if not handler_name:
                continue
            handler = handler_lookup.get(handler_name)
            if handler is None:
                continue
            bindings[capability_id] = handler
        self._handlers = bindings
        return bindings

    # -------------------------------------------------------------------------
    def get_handler(self, tool_id: str) -> ToolHandler | None:
        if not self._handlers:
            self.load_tool_bindings()
        return self._handlers.get(tool_id)

    # -------------------------------------------------------------------------
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
