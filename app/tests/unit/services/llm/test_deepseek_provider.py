from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic import BaseModel

from server.prompts.providers import build_deepseek_json_schema_instruction
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.types import LLMRequest


###############################################################################
class _StructuredPayload(BaseModel):
    answer: str


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
def test_structured_output_uses_deepseek_json_object_mode(monkeypatch) -> None:
    client = _Client()
    provider = DeepSeekProvider(api_key="test")
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-chat",
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
    assert '"answer"' in call["messages"][-1]["content"]
    assert sum("JSON schema" in str(message.get("content")) for message in call["messages"]) == 1
    assert call["messages"][-1]["content"] == build_deepseek_json_schema_instruction(
        _StructuredPayload.model_json_schema()
    )
