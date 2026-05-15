from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic import BaseModel

from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest, LLMResult


class _StructuredPayload(BaseModel):
    answer: str = "structured"


class _Message:
    def __init__(self, content) -> None:  # noqa: ANN001
        self.content = content
        self.response_metadata = {"provider": "fake"}
        self.usage_metadata = {"total_tokens": 3}
        self.additional_kwargs = {}


class _StructuredModel:
    def __init__(self, schema: type[object]) -> None:
        self._schema = schema

    def invoke(self, _messages):  # noqa: ANN001, ANN202
        validator = getattr(self._schema, "model_validate", None)
        if callable(validator):
            return validator({"answer": "structured"})
        return {"answer": "structured"}


class _FakeChatModel:
    instances: list["_FakeChatModel"] = []

    def __init__(self, **_kwargs) -> None:
        self.kwargs = _kwargs
        self.instances.append(self)

    def invoke(self, _messages):  # noqa: ANN001, ANN202
        return _Message("chat-ok")

    def stream(self, _messages):  # noqa: ANN001, ANN202
        yield _Message([{"text": "chunk-1"}])
        yield _Message("chunk-2")

    def with_structured_output(self, schema: type[object]) -> _StructuredModel:
        return _StructuredModel(schema)


class _FakeEmbeddings:
    def __init__(self, **_kwargs) -> None:
        pass

    def embed_query(self, _input_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FakeOpenAIResponse:
    output_text = "chat-ok"

    def model_dump(self, *, mode: str) -> dict[str, object]:
        return {"mode": mode, "id": "resp-test"}


class _FakeOpenAIResponses:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.parse_calls: list[dict[str, object]] = []

    def create(self, **kwargs):  # noqa: ANN001, ANN202
        self.create_calls.append(kwargs)
        if kwargs.get("stream"):
            return [
                SimpleNamespace(type="response.output_text.delta", delta="chunk-1"),
                SimpleNamespace(type="response.created", delta="ignored"),
                SimpleNamespace(type="response.output_text.delta", delta="chunk-2"),
            ]
        return _FakeOpenAIResponse()

    def parse(self, **kwargs):  # noqa: ANN001, ANN202
        self.parse_calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=_StructuredPayload(answer="structured"),
            output_text="",
        )


class _FakeOpenAIEmbeddingEndpoint:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []

    def create(self, **kwargs):  # noqa: ANN001, ANN202
        self.create_calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class _FakeOpenAIClient:
    instances: list["_FakeOpenAIClient"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.responses = _FakeOpenAIResponses()
        self.embeddings = _FakeOpenAIEmbeddingEndpoint()
        self.instances.append(self)


class _FakeGoogleModels:
    def __init__(self) -> None:
        self.generate_content_calls: list[dict[str, object]] = []
        self.generate_content_stream_calls: list[dict[str, object]] = []
        self.embed_content_calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):  # noqa: ANN001, ANN202
        self.generate_content_calls.append(kwargs)
        config = kwargs.get("config")
        if isinstance(config, dict) and config.get("response_mime_type"):
            return SimpleNamespace(text=json.dumps({"answer": "structured"}))
        return SimpleNamespace(text="chat-ok", model_dump=lambda mode: {"mode": mode})

    def generate_content_stream(self, **kwargs):  # noqa: ANN001, ANN202
        self.generate_content_stream_calls.append(kwargs)
        return [SimpleNamespace(text="chunk-1"), SimpleNamespace(text="chunk-2")]

    def embed_content(self, **kwargs):  # noqa: ANN001, ANN202
        self.embed_content_calls.append(kwargs)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3])]
        )


class _FakeGoogleClient:
    instances: list["_FakeGoogleClient"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.models = _FakeGoogleModels()
        self.instances.append(self)


class _FakeHttpOptions:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def _request() -> LLMRequest:
    return LLMRequest(
        model="test-model",
        messages=[
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ],
    )


def test_openai_provider_uses_responses_api(monkeypatch) -> None:
    _FakeOpenAIClient.instances = []
    monkeypatch.setattr("server.services.llm.openai_provider.OpenAI", _FakeOpenAIClient)
    provider = OpenAIProvider(api_key="k", base_url="https://api.openai.test/v1")

    response = provider.chat(_request())
    assert isinstance(response, LLMResult)
    assert response.content == "chat-ok"
    assert list(provider.stream_chat(_request())) == ["chunk-1", "chunk-2"]
    assert provider.structured_output(_request(), schema=_StructuredPayload) == {
        "answer": "structured"
    }
    assert provider.embeddings(model="embed-model", input_text="hello") == [
        0.1,
        0.2,
        0.3,
    ]

    first_client = _FakeOpenAIClient.instances[0]
    assert first_client.kwargs == {
        "api_key": "k",
        "base_url": "https://api.openai.test/v1",
    }
    assert first_client.responses.create_calls[0]["model"] == "test-model"
    assert first_client.responses.create_calls[0]["input"] == _request().messages
    assert _FakeOpenAIClient.instances[2].responses.parse_calls[0]["text_format"] is _StructuredPayload
    assert _FakeOpenAIClient.instances[3].embeddings.create_calls[0] == {
        "model": "embed-model",
        "input": "hello",
    }


def test_google_provider_uses_genai_sdk(monkeypatch) -> None:
    _FakeGoogleClient.instances = []
    monkeypatch.setattr("server.services.llm.google_provider.genai.Client", _FakeGoogleClient)
    monkeypatch.setattr(
        "server.services.llm.google_provider.genai_types.HttpOptions",
        _FakeHttpOptions,
    )
    provider = GoogleProvider(api_key="k", base_url="https://google.example/v1beta")

    response = provider.chat(_request())
    assert isinstance(response, LLMResult)
    assert response.content == "chat-ok"
    assert list(provider.stream_chat(_request())) == ["chunk-1", "chunk-2"]
    assert provider.structured_output(_request(), schema=_StructuredPayload) == {
        "answer": "structured"
    }
    assert provider.embeddings(model="embed-model", input_text="hello") == [
        0.1,
        0.2,
        0.3,
    ]

    first_client = _FakeGoogleClient.instances[0]
    assert first_client.kwargs["api_key"] == "k"
    assert first_client.kwargs["http_options"].kwargs == {
        "baseUrl": "https://google.example/v1beta",
        "apiVersion": "v1beta",
    }
    chat_call = first_client.models.generate_content_calls[0]
    assert chat_call["model"] == "test-model"
    assert chat_call["contents"] == [
        {"role": "user", "parts": [{"text": "Hello"}]},
    ]
    assert chat_call["config"] == {
        "temperature": 0.2,
        "system_instruction": "System prompt",
    }
    structured_call = _FakeGoogleClient.instances[2].models.generate_content_calls[0]
    assert structured_call["config"]["response_mime_type"] == "application/json"
    assert "response_json_schema" in structured_call["config"]
    assert _FakeGoogleClient.instances[3].models.embed_content_calls[0] == {
        "model": "embed-model",
        "contents": "hello",
    }


def test_ollama_provider_langchain_paths(monkeypatch) -> None:
    _FakeChatModel.instances = []
    monkeypatch.setattr(
        "server.services.llm.ollama.ChatOllama",
        _FakeChatModel,
    )
    monkeypatch.setattr(
        "server.services.llm.ollama.OllamaEmbeddings",
        _FakeEmbeddings,
    )
    provider = OllamaProvider(base_url="http://localhost:11434")

    response = provider.chat(_request())
    assert isinstance(response, LLMResult)
    assert response.content == "chat-ok"
    assert list(provider.stream_chat(_request())) == ["chunk-1", "chunk-2"]
    assert provider.structured_output(_request(), schema=_StructuredPayload) == {
        "answer": "structured"
    }
    assert provider.embeddings(model="embed-model", input_text="hello") == [
        0.1,
        0.2,
        0.3,
    ]
    assert _FakeChatModel.instances[0].kwargs["num_ctx"] >= 2048
    assert provider.last_context_usage is not None
    assert provider.last_context_usage["provider"] == "ollama"
