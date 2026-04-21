from __future__ import annotations

from pydantic import BaseModel

from AEGIS.server.services.llm.google_provider import GoogleProvider
from AEGIS.server.services.llm.ollama import OllamaProvider
from AEGIS.server.services.llm.openai_provider import OpenAIProvider
from AEGIS.server.services.llm.types import ChatCompletionRequest, ChatCompletionResult


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
    def __init__(self, **_kwargs) -> None:
        pass

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


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="test-model",
        messages=[{"role": "user", "content": "Hello"}],
    )


def test_openai_provider_langchain_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.llm.openai_provider.ChatOpenAI", _FakeChatModel
    )
    monkeypatch.setattr(
        "AEGIS.server.services.llm.openai_provider.OpenAIEmbeddings", _FakeEmbeddings
    )
    provider = OpenAIProvider(api_key="k", base_url="https://api.openai.test/v1")

    response = provider.chat(_request())
    assert isinstance(response, ChatCompletionResult)
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


def test_google_provider_langchain_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.llm.google_provider.ChatGoogleGenerativeAI",
        _FakeChatModel,
    )
    monkeypatch.setattr(
        "AEGIS.server.services.llm.google_provider.GoogleGenerativeAIEmbeddings",
        _FakeEmbeddings,
    )
    provider = GoogleProvider(api_key="k", base_url="https://google.example")

    response = provider.chat(_request())
    assert isinstance(response, ChatCompletionResult)
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


def test_ollama_provider_langchain_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.llm.ollama.ChatOllama",
        _FakeChatModel,
    )
    monkeypatch.setattr(
        "AEGIS.server.services.llm.ollama.OllamaEmbeddings",
        _FakeEmbeddings,
    )
    provider = OllamaProvider(base_url="http://localhost:11434")

    response = provider.chat(_request())
    assert isinstance(response, ChatCompletionResult)
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
