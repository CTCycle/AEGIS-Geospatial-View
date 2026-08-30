from __future__ import annotations

import json
from types import SimpleNamespace

from server.domain.agent.tools import ToolError, ToolExecutionEnvelope
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.opencode_provider import OPENCODE_GO_PROVIDER, OpenCodeProvider
from server.services.llm.types import LLMRequest, LLMToolDefinition


###############################################################################
def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="resolve_location",
        description="Resolve a place name.",
        parameters_json_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


###############################################################################
def _request(provider: str, model: str) -> LLMRequest:
    return LLMRequest(
        provider=provider,
        model=model,
        messages=[{"role": "user", "content": "Find Zurich."}],
        tools=[_tool()],
    )


###############################################################################
class _Completions:
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        message = SimpleNamespace(
            content="",
            tool_calls=[
                SimpleNamespace(
                    id="call-1",
                    function=SimpleNamespace(
                        name="resolve_location",
                        arguments=json.dumps({"query": "Zurich"}),
                    ),
                )
            ],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
            model_dump=lambda mode="json": {"choices": []},
        )


###############################################################################
class _OpenAICompatibleClient:
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.completions = _Completions()
        self.chat = SimpleNamespace(completions=self.completions)


###############################################################################
def test_google_native_tool_contract_uses_function_declarations() -> None:
    contents = GoogleProvider._contents_from_messages(
        [
            {
                "role": "assistant",
                "tool_calls": [{"name": "resolve_location", "arguments": {}}],
            },
            {"role": "tool", "name": "resolve_location", "content": '{"ok":true}'},
        ]
    )
    schema = GoogleProvider.tool_to_google_schema(_tool())
    assert schema["parameters"]["required"] == ["query"]
    assert contents[0]["role"] == "model"
    assert contents[1]["parts"][0]["function_response"]["name"] == "resolve_location"


###############################################################################
def test_deepseek_and_opencode_chat_contracts_are_chat_completions_native(
    monkeypatch,
) -> None:
    for provider, model in (
        (
            DeepSeekProvider(api_key="test", base_url="https://deepseek.test"),
            "deepseek-chat",
        ),
        (
            OpenCodeProvider(api_key="test", provider_name=OPENCODE_GO_PROVIDER),
            "deepseek-v4-flash",
        ),
    ):
        client = _OpenAICompatibleClient()
        monkeypatch.setattr(provider, "_client", lambda client=client: client)
        result = provider.chat(_request(provider.provider_name, model))
        call = client.completions.calls[0]
        assert call["tools"][0]["type"] == "function"
        assert call["tool_choice"] == "auto"
        assert result.tool_calls[0].arguments == {"query": "Zurich"}


###############################################################################
def test_ollama_chat_contract_emits_native_tools_and_parses_results() -> None:
    captured: dict[str, object] = {}

    ###############################################################################
    class _Provider(OllamaProvider):
        # -------------------------------------------------------------------------
        def supports_tools(self, model: str) -> bool:
            _ = model
            return True

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict[str, object]):
            captured["path"] = path
            captured["payload"] = payload
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "resolve_location",
                                "arguments": {"query": "Zurich"},
                            },
                        }
                    ],
                }
            }

    provider = _Provider(base_url="http://ollama.test")
    result = provider.chat(_request("ollama", "llama3.2"))
    assert captured["path"] == "/api/chat"
    assert captured["payload"]["tools"][0]["function"]["name"] == "resolve_location"
    assert result.tool_calls[0].arguments == {"query": "Zurich"}


###############################################################################
def test_provider_contract_envelope_error_remains_structured() -> None:
    envelope = ToolExecutionEnvelope(
        ok=False,
        error=ToolError(code="provider_unavailable", message="upstream unavailable"),
    )
    assert envelope.to_dict()["error"] == {
        "code": "provider_unavailable",
        "message": "upstream unavailable",
    }
