from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic import BaseModel

from server.services.llm.opencode_provider import (
    OPENCODE_GO_PROVIDER,
    OPENCODE_PROVIDER,
    OpenCodeProvider,
)
from server.services.llm.types import LLMRequest

###############################################################################
class _StructuredPayload(BaseModel):
    answer: str

###############################################################################
class _Response:

    # -------------------------------------------------------------------------
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    # -------------------------------------------------------------------------
    def raise_for_status(self) -> None:
        return None

    # -------------------------------------------------------------------------
    def json(self) -> dict[str, object]:
        return self.payload

###############################################################################
class _Completions:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        message = SimpleNamespace(
            content=json.dumps({"answer": "structured"}),
            tool_calls=[],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")]
        )

###############################################################################
class _Client:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.completions = _Completions()
        self.chat = SimpleNamespace(completions=self.completions)

###############################################################################
def test_zen_catalog_filters_models_to_openai_compatible_subset(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs):  # noqa: ANN003, ANN202
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Response(
            {
                "data": [
                    {"id": "deepseek-v4-flash", "owned_by": "opencode"},
                    {"id": "claude-opus-5", "owned_by": "opencode"},
                ]
            }
        )

    monkeypatch.setattr("server.services.llm.opencode_provider.httpx.get", fake_get)
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_PROVIDER)

    models = provider.list_models()

    assert [model.name for model in models] == ["deepseek-v4-flash"]
    assert models[0].provider == OPENCODE_PROVIDER
    assert models[0].metadata["protocol"] == "openai-chat-completions"
    assert captured["url"] == "https://opencode.ai/zen/v1/models"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-key"

###############################################################################
def test_go_uses_go_endpoint_and_exposes_tool_capabilities() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    assert provider.base_url == "https://opencode.ai/zen/go/v1"
    assert provider.supports_tools("deepseek-v4-flash") is True
    assert provider.supports_structured_output("deepseek-v4-flash") is True
    assert provider.supports_tools("claude-opus-5") is False

###############################################################################
def test_structured_output_uses_chat_completions_json_object_mode(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_PROVIDER)
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": "Extract the answer."},
            {"role": "user", "content": "Hello"},
        ],
    )

    result = provider.structured_output(request, schema=_StructuredPayload)

    assert result == {"answer": "structured"}
    call = client.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert "JSON schema" in call["messages"][-1]["content"]
