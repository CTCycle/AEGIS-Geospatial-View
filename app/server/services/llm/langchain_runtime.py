from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from server.services.llm.types import LLMRequest, LLMResult


def to_langchain_messages(messages: list[dict[str, str]]) -> list[object]:
    mapped: list[object] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "")
        if role == "system":
            mapped.append(SystemMessage(content=content))
            continue
        if role == "assistant":
            mapped.append(AIMessage(content=content))
            continue
        mapped.append(HumanMessage(content=content))
    return mapped


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    chunks.append(item)
                continue
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str) and text_value:
                    chunks.append(text_value)
        return "".join(chunks)
    return ""


def read_ai_message_text(value: object) -> str:
    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if content is None:
        return str(value)
    return _text_from_content(content)


def invoke_chat_model(*, chat_model: object, request: LLMRequest) -> LLMResult:
    response = chat_model.invoke(to_langchain_messages(request.messages))
    return LLMResult(
        content=read_ai_message_text(response),
        raw={
            "response_metadata": dict(getattr(response, "response_metadata", {}) or {}),
            "usage_metadata": dict(getattr(response, "usage_metadata", {}) or {}),
            "additional_kwargs": dict(getattr(response, "additional_kwargs", {}) or {}),
        },
    )


def stream_chat_model(
    *, chat_model: object, request: LLMRequest
) -> Iterable[str]:
    for chunk in chat_model.stream(to_langchain_messages(request.messages)):
        text = read_ai_message_text(chunk)
        if text:
            yield text


def invoke_structured_chat_model(
    *,
    chat_model: object,
    request: LLMRequest,
    schema: type[object],
) -> dict[str, object]:
    structured_model = chat_model.with_structured_output(schema)
    payload = structured_model.invoke(to_langchain_messages(request.messages))
    if isinstance(payload, dict):
        return payload
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    to_dict = getattr(payload, "dict", None)
    if callable(to_dict):
        dumped = to_dict()
        return dumped if isinstance(dumped, dict) else {}
    return {}
