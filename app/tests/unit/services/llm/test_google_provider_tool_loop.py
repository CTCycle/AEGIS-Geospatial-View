from __future__ import annotations

import pytest
from types import SimpleNamespace

from server.services.llm.errors import LLMRequestSchemaError
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.types import LLMRequest, LLMToolDefinition

###############################################################################
def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="describe_geospatial_capability",
        description="Describe capability",
        parameters_json_schema={
            "type": "object",
            "properties": {"capability_id": {"type": "string"}},
            "required": ["capability_id"],
        },
    )

###############################################################################
def test_google_converts_aegis_tools_into_declarations() -> None:
    assert GoogleProvider.tool_to_google_schema(_tool()) == {
        "name": "describe_geospatial_capability",
        "description": "Describe capability",
        "parameters": {
            "type": "object",
            "properties": {"capability_id": {"type": "string"}},
            "required": ["capability_id"],
        },
    }


###############################################################################
def test_google_reads_selected_model_limits_from_models_api(monkeypatch) -> None:
    client = SimpleNamespace(
        models=SimpleNamespace(
            get=lambda **_kwargs: {
                "inputTokenLimit": 1_048_576,
                "outputTokenLimit": 65_536,
            }
        ),
        close=lambda: None,
    )
    provider = GoogleProvider(api_key="test")
    monkeypatch.setattr(provider, "_client", lambda **_kwargs: client)

    metadata = provider.get_model_context_metadata("gemini-2.5-flash")

    assert metadata["context_window_tokens"] == 1_048_576
    assert metadata["maximum_output_tokens"] == 65_536
    assert metadata["context_metadata_authority"] == "provider"

###############################################################################
def test_google_parses_function_calls() -> None:
    calls = GoogleProvider._parse_tool_calls(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "1",
                                    "name": "describe_geospatial_capability",
                                    "args": {"capability_id": "rain"},
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert calls[0].name == "describe_geospatial_capability"
    assert calls[0].arguments == {"capability_id": "rain"}

###############################################################################
def test_google_converts_tool_results_to_function_responses() -> None:
    contents = GoogleProvider._contents_from_messages(
        [
            {
                "role": "tool",
                "name": "describe_geospatial_capability",
                "tool_call_id": "1",
                "content": '{"ok":true}',
            }
        ]
    )

    assert contents == [
        {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "id": "1",
                        "name": "describe_geospatial_capability",
                        "response": {"content": '{"ok":true}'},
                    }
                }
            ],
        }
    ]

###############################################################################
def test_google_classifies_tools_plus_response_schema_at_provider_boundary() -> None:
    request = LLMRequest(
        model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "x"}],
        tools=[_tool()],
        response_json_schema={"type": "object", "properties": {}},
    )
    with pytest.raises(LLMRequestSchemaError) as error:
        GoogleProvider(api_key="test")._validate_request_capabilities(request)
    assert error.value.category == "schema_definition"


###############################################################################
def test_native_parts_survive_sequential_parallel_checkpoint_continuation() -> None:
    import json

    from google.genai import types as genai_types
    from server.domain.agent.capability_route import AgentRunState
    from server.domain.llm.types import LLMResult
    from server.services.agent.agent_loop import AgentLoop

    history = []
    for step in range(10):
        content = genai_types.Content(
            role="model",
            parts=[
                genai_types.Part(text="private", thought=True),
                genai_types.Part(
                    function_call=genai_types.FunctionCall(id=f"{step}-a", name="foo", args={}),
                    thought_signature=f"signature-{step}".encode(),
                ),
                genai_types.Part(function_call=genai_types.FunctionCall(id=f"{step}-b", name="foo", args={})),
            ],
        )
        response = genai_types.GenerateContentResponse(
            candidates=[genai_types.Candidate(content=content)]
        )
        raw = response.model_dump(mode="json", exclude_none=True)
        result = LLMResult(
            content="",
            tool_calls=GoogleProvider._parse_tool_calls(raw),
            provider_continuation=GoogleProvider._continuation_content(response),
        )
        history.extend(AgentLoop._assistant_and_tool_messages(result))
        history.extend(
            {"role": "tool", "name": "foo", "tool_call_id": call.id, "content": "ok"}
            for call in result.tool_calls
        )
    state = AgentRunState(request_id="r", conversation_id="c", user_message="test", phase="execute_tool")
    state.provider_continuation = AgentLoop._protocol_messages(history)
    restored = AgentRunState.from_checkpoint(json.loads(json.dumps(state.checkpoint())))
    contents = GoogleProvider._contents_from_messages(restored.provider_continuation)
    assert len(contents) == 20
    for step in range(10):
        model_content = genai_types.Content.model_validate(contents[step * 2])
        assert model_content.parts[0].thought is True
        assert model_content.parts[1].thought_signature == f"signature-{step}".encode()
        assert [part.function_call.id for part in model_content.parts[1:]] == [f"{step}-a", f"{step}-b"]
        assert [part["function_response"]["id"] for part in contents[step * 2 + 1]["parts"]] == [f"{step}-a", f"{step}-b"]


###############################################################################
def test_only_first_google_candidate_is_executed() -> None:
    raw = {"candidates": [
        {"content": {"parts": [{"function_call": {"id": name, "name": name, "args": {}}}]} }
        for name in ("chosen", "alternative")
    ]}
    assert [call.name for call in GoogleProvider._parse_tool_calls(raw)] == ["chosen"]
