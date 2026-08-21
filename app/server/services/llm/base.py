from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any

from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolDefinition,
    ModelDescriptor,
)
from server.services.llm.errors import LLMRequestSchemaError, LLMStructuredOutputError

###############################################################################
class LLMProvider(ABC):
    provider_name: str

    # -------------------------------------------------------------------------
    @abstractmethod
    def list_models(self) -> list[ModelDescriptor]: ...

    # -------------------------------------------------------------------------
    @abstractmethod
    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    # -------------------------------------------------------------------------
    @abstractmethod
    def stream_chat(self, request: LLMRequest) -> Iterable[str]: ...

    # -------------------------------------------------------------------------
    @abstractmethod
    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]: ...

    # -------------------------------------------------------------------------
    @abstractmethod
    def embeddings(self, *, model: str, input_text: str) -> list[float]: ...

    # -------------------------------------------------------------------------
    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        _ = model
        return None

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        _ = model
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages

    # -------------------------------------------------------------------------
    def _validate_request_capabilities(self, request: LLMRequest) -> None:
        if request.tools and request.response_json_schema is not None:
            raise LLMRequestSchemaError(
                provider=self.provider_name,
                model=request.model,
                stage="request_validation",
                detail="Native tools cannot be combined with a structured response schema.",
            )
        for tool in request.tools or []:
            if (
                not isinstance(tool.name, str)
                or not tool.name.strip()
                or not self._is_json_schema(tool.parameters_json_schema)
            ):
                raise LLMRequestSchemaError(
                    provider=self.provider_name,
                    model=request.model,
                    stage="tool_definition",
                    detail="A native tool definition has an invalid name or parameters schema.",
                )
        if request.response_json_schema is not None and not self._is_json_schema(
            request.response_json_schema
        ):
            raise LLMRequestSchemaError(
                provider=self.provider_name,
                model=request.model,
                stage="response_schema",
                detail="The structured response schema is not a JSON object.",
            )
        request_tool_state = request.metadata.get("supports_tools")
        supports_tools = (
            request_tool_state
            if isinstance(request_tool_state, bool)
            else self.supports_tools(request.model)
        )
        if request.tools and supports_tools is False:
            raise LLMStructuredOutputError(
                category="model_capability",
                provider=self.provider_name,
                model=request.model,
                stage="tool_calling",
                code="model_tools_unsupported",
                detail=(
                    f"Model '{request.model}' for provider '{self.provider_name}' "
                    "does not support native tools."
                ),
            )
        request_structured_state = request.metadata.get("supports_structured_output")
        supports_structured_output = (
            request_structured_state
            if isinstance(request_structured_state, bool)
            else self.supports_structured_output(request.model)
        )
        if request.response_json_schema is not None and supports_structured_output is False:
            raise LLMStructuredOutputError(
                category="model_capability",
                provider=self.provider_name,
                model=request.model,
                stage="structured_output",
                code="model_structured_output_unsupported",
                detail=(
                    f"Model '{request.model}' for provider '{self.provider_name}' "
                    "does not support structured output."
                ),
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_json_schema(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        schema_type = value.get("type")
        if schema_type is not None and schema_type not in {
            "array",
            "boolean",
            "integer",
            "null",
            "number",
            "object",
            "string",
        }:
            return False
        properties = value.get("properties")
        if properties is not None and not isinstance(properties, dict):
            return False
        required = value.get("required")
        if required is not None and (
            not isinstance(required, list)
            or not all(isinstance(item, str) and item.strip() for item in required)
        ):
            return False
        items = value.get("items")
        if items is not None and not isinstance(items, dict):
            return False
        return True
