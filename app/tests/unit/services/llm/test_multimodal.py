from __future__ import annotations

import pytest

from server.services.llm.context_budget import estimate_message_tokens
from server.services.llm.multimodal import (
    IMAGE_TOKEN_ESTIMATE,
    attach_image,
    messages_contain_image,
    normalize_image_content_for_google,
    normalize_image_content_for_ollama,
    normalize_image_content_for_openai_chat,
    normalize_image_content_for_openai_responses,
    text_from_multimodal_content,
)


###############################################################################
def _base64() -> str:
    return "QUJDRA=="


###############################################################################
def test_attach_image_appends_a_user_message_with_caption_and_image() -> None:
    messages: list[dict[str, object]] = [
        {"role": "system", "content": "system"},
    ]
    result = attach_image(
        messages,
        data=_base64(),
        mime_type="image/jpeg",
        caption="Captured map render map-1:2.",
    )

    assert len(result) == 2
    user = result[-1]
    assert user["role"] == "user"
    content = user["content"]
    assert isinstance(content, list)
    assert content[0] == {
        "type": "text",
        "text": "Captured map render map-1:2.",
    }
    assert content[1] == {
        "type": "image",
        "mime_type": "image/jpeg",
        "data": _base64(),
    }
    assert messages_contain_image(result) is True
    assert messages_contain_image(messages) is False


###############################################################################
def test_attach_image_rejects_unsupported_mime_and_empty_data() -> None:
    base = [{"role": "user", "content": "hello"}]
    with pytest.raises(ValueError, match="mime"):
        attach_image(base, data=_base64(), mime_type="image/gif", caption="x")
    unchanged = attach_image(base, data="", mime_type="image/jpeg", caption="x")
    assert unchanged == base


###############################################################################
def test_openai_responses_projection() -> None:
    content = [
        {"type": "text", "text": "Inspect the map."},
        {"type": "image", "mime_type": "image/jpeg", "data": _base64()},
    ]
    items = normalize_image_content_for_openai_responses(content)
    assert items == [
        {"type": "input_text", "text": "Inspect the map."},
        {
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{_base64()}",
        },
    ]
    assert normalize_image_content_for_openai_responses("plain text") is None


###############################################################################
def test_openai_chat_projection() -> None:
    content = [
        {"type": "text", "text": "Look."},
        {"type": "image", "mime_type": "image/png", "data": _base64()},
    ]
    parts = normalize_image_content_for_openai_chat(content)
    assert parts == [
        {"type": "text", "text": "Look."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{_base64()}"},
        },
    ]


###############################################################################
def test_google_projection() -> None:
    content = [
        {"type": "text", "text": "Analyze."},
        {"type": "image", "mime_type": "image/jpeg", "data": _base64()},
    ]
    parts = normalize_image_content_for_google(content)
    assert parts == [
        {"text": "Analyze."},
        {"inline_data": {"mime_type": "image/jpeg", "data": _base64()}},
    ]


###############################################################################
def test_ollama_projection_strips_data_url_prefix() -> None:
    content = [
        {"type": "text", "text": "See it."},
        {"type": "image", "mime_type": "image/jpeg", "data": _base64()},
    ]
    text, images = normalize_image_content_for_ollama(content)
    assert text == "See it."
    assert images == [_base64()]

    prefixed = [
        {"type": "image", "mime_type": "image/jpeg", "data": f"data:image/jpeg;base64,{_base64()}"}
    ]
    _text, prefixed_images = normalize_image_content_for_ollama(prefixed)
    assert prefixed_images == [_base64()]


###############################################################################
def test_text_projection_handles_string_and_part_lists() -> None:
    assert text_from_multimodal_content("plain") == "plain"
    assert (
        text_from_multimodal_content(
            [
                {"type": "text", "text": "a"},
                {"type": "image", "mime_type": "image/jpeg", "data": _base64()},
                {"type": "text", "text": "b"},
            ]
        )
        == "a b"
    )


###############################################################################
def test_image_tokens_are_counted_in_message_budget() -> None:
    text_only = [{"role": "user", "content": "hello world"}]
    with_image = attach_image(
        list(text_only),
        data=_base64(),
        mime_type="image/jpeg",
        caption="Map capture.",
    )

    text_tokens = estimate_message_tokens(text_only)
    image_tokens = estimate_message_tokens(with_image)
    assert image_tokens >= text_tokens + IMAGE_TOKEN_ESTIMATE