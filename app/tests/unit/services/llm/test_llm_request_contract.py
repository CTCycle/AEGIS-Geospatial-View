from __future__ import annotations

import pytest

from server.services.llm.types import LLMRequest, LLMToolDefinition


def test_llm_request_rejects_tools_plus_structured_schema() -> None:
    tool = LLMToolDefinition(
        name="lookup",
        description="Lookup",
        parameters_json_schema={"type": "object", "properties": {}},
    )

    with pytest.raises(
        ValueError,
        match="LLMRequest cannot combine native tools with structured response_schema",
    ):
        LLMRequest(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            tools=[tool],
            response_json_schema={"type": "object", "properties": {}},
        )

