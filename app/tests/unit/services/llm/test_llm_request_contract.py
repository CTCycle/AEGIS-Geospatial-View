from __future__ import annotations

from server.services.llm.types import LLMRequest, LLMToolDefinition


###############################################################################
def test_llm_request_preserves_tools_and_schema_for_provider_validation() -> None:
    tool = LLMToolDefinition(
        name="lookup",
        description="Lookup",
        parameters_json_schema={"type": "object", "properties": {}},
    )

    request = LLMRequest(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        tools=[tool],
        response_json_schema={"type": "object", "properties": {}},
    )
    assert request.tools == [tool]
    assert request.response_json_schema == {"type": "object", "properties": {}}
