from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

###############################################################################
# Canonical neutral content-part schema.
#
# Messages remain plain ``dict``s with a ``content`` field.  When ``content``
# is a ``list`` it carries multimodal parts:
#
#     {"type": "text", "text": "..."}
#     {"type": "image", "mime_type": "image/jpeg", "data": "<base64>"}
#
# Providers map this neutral shape into their native request bodies
# (``input_image``/``inline_data``/``images``/``image_url``).  Keeping the
# shape provider-agnostic makes vision a reusable model capability rather than
# a screenshot-specific special case.
###############################################################################

SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# Conservative per-image token estimate used by the context budget when the
# provider has not reported exact usage.  Images are downscaled server-side
# before they reach this module, so this bound stays small and predictable.
IMAGE_TOKEN_ESTIMATE = 1024

TEXT_PART_TYPE = "text"
IMAGE_PART_TYPE = "image"

###############################################################################
def is_multimodal_content(content: object) -> bool:
    """True when ``content`` is a list of typed parts (not a plain string)."""

    return isinstance(content, list) and bool(content)


###############################################################################
def iter_image_parts(content: object) -> Iterator[dict[str, Any]]:
    """Yield image parts from a neutral multimodal ``content`` value."""

    if not is_multimodal_content(content):
        return
    for raw_item in content:
        item = raw_item if isinstance(raw_item, dict) else None
        if item and item.get("type") == IMAGE_PART_TYPE:
            data = item.get("data")
            if isinstance(data, str) and data.strip():
                yield item


###############################################################################
def iter_text_parts(content: object) -> Iterator[str]:
    """Yield the text fragments of a neutral multimodal ``content`` value."""

    if not is_multimodal_content(content):
        return
    for raw_item in content:
        item = raw_item if isinstance(raw_item, dict) else None
        if item and item.get("type") == TEXT_PART_TYPE:
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                yield text


###############################################################################
def content_has_image(content: object) -> bool:
    return any(True for _ in iter_image_parts(content))


###############################################################################
def messages_contain_image(messages: Iterable[dict[str, Any]]) -> bool:
    return any(content_has_image(message.get("content")) for message in messages)


###############################################################################
def image_data_url(
    data: str,
    *,
    mime_type: str,
) -> str:
    """Serialize one base64 image part as a data URL (OpenAI/DeepSeek form)."""

    return f"data:{mime_type};base64,{data}"


###############################################################################
def attach_image(
    messages: list[dict[str, Any]],
    *,
    data: str,
    mime_type: str,
    caption: str,
) -> list[dict[str, Any]]:
    """Append one user message carrying a neutral image part plus a caption.

    The caption tells the model what the image represents without duplicating
    the complete structured map state (which the working-state message and the
    canonical context already carry).
    """

    if not isinstance(data, str) or not data.strip():
        return messages
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError(
            f"Unsupported vision image mime type '{mime_type}'. "
            f"Supported: {sorted(SUPPORTED_IMAGE_MIME_TYPES)}."
        )
    parts: list[dict[str, Any]] = [{"type": TEXT_PART_TYPE, "text": caption}]
    parts.append(
        {"type": IMAGE_PART_TYPE, "mime_type": mime_type, "data": data}
    )
    return [*messages, {"role": "user", "content": parts}]


###############################################################################
def image_part_count(messages: Iterable[dict[str, Any]]) -> int:
    """Count image parts across the message list (for telemetry/budget)."""

    return sum(
        1
        for message in messages
        for _ in iter_image_parts(message.get("content"))
    )


###############################################################################
def estimate_image_tokens(messages: Iterable[dict[str, Any]]) -> int:
    """Token allowance for image parts across the message list."""

    return image_part_count(messages) * IMAGE_TOKEN_ESTIMATE


###############################################################################
def text_from_multimodal_content(content: object) -> str:
    """Return the text projection of a neutral content value.

    Plain string content is returned unchanged; list content is joined from
    its text parts (used by token estimators and legacy stringifiers).
    """

    if isinstance(content, str):
        return content
    if is_multimodal_content(content):
        return " ".join(iter_text_parts(content)).strip()
    return ""


###############################################################################
def _normalize_part_list(
    content: object,
) -> list[dict[str, Any]] | None:
    """Return the raw part list when content is a JSON array of objects."""

    if not isinstance(content, list):
        return None
    if not all(isinstance(item, dict) for item in content):
        return None
    return list(content)


###############################################################################
def normalize_image_content_for_ollama(
    content: object,
) -> tuple[str, list[str]]:
    """Split neutral content into Ollama's ``(text, images)`` form.

    Returns the plain text plus a list of base64 image payloads (the data URL
    prefix, if present, is stripped because Ollama expects raw base64).
    """

    text = text_from_multimodal_content(content)
    images: list[str] = []
    for item in iter_image_parts(content):
        data = str(item.get("data") or "").strip()
        if "," in data and data.startswith(("data:", "data:image")):
            data = data.split(",", 1)[1]
        if data:
            images.append(data)
    return text, images


###############################################################################
def normalize_image_content_for_openai_chat(
    content: object,
) -> list[dict[str, Any]] | None:
    """Project neutral content into OpenAI chat-completions parts.

    Returns ``None`` when there is nothing to project (plain string or empty).
    Text parts become ``{"type": "text", "text": ...}`` and image parts become
    ``{"type": "image_url", "image_url": {"url": data_url}}``.
    """

    raw_parts = _normalize_part_list(content)
    if raw_parts is None:
        return None
    parts: list[dict[str, Any]] = []
    for raw in raw_parts:
        part_type = str(raw.get("type") or "")
        if part_type == TEXT_PART_TYPE:
            text = raw.get("text")
            if isinstance(text, str) and text.strip():
                parts.append({"type": "text", "text": text})
        elif part_type == IMAGE_PART_TYPE:
            data = raw.get("data")
            mime_type = str(raw.get("mime_type") or "image/jpeg")
            if isinstance(data, str) and data.strip():
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url(data, mime_type=mime_type)
                        },
                    }
                )
    return parts or None


###############################################################################
def normalize_image_content_for_openai_responses(
    content: object,
) -> list[dict[str, Any]] | None:
    """Project neutral content into OpenAI Responses input items.

    Text parts become ``input_text`` and image parts become ``input_image``
    items carrying the data URL.
    """

    raw_parts = _normalize_part_list(content)
    if raw_parts is None:
        return None
    items: list[dict[str, Any]] = []
    for raw in raw_parts:
        part_type = str(raw.get("type") or "")
        if part_type == TEXT_PART_TYPE:
            text = raw.get("text")
            if isinstance(text, str) and text.strip():
                items.append({"type": "input_text", "text": text})
        elif part_type == IMAGE_PART_TYPE:
            data = raw.get("data")
            mime_type = str(raw.get("mime_type") or "image/jpeg")
            if isinstance(data, str) and data.strip():
                items.append(
                    {
                        "type": "input_image",
                        "image_url": image_data_url(data, mime_type=mime_type),
                    }
                )
    return items or None


###############################################################################
def normalize_image_content_for_google(
    content: object,
) -> list[dict[str, Any]] | None:
    """Project neutral content into Google ``parts`` (inline_data images)."""

    raw_parts = _normalize_part_list(content)
    if raw_parts is None:
        return None
    parts: list[dict[str, Any]] = []
    for raw in raw_parts:
        part_type = str(raw.get("type") or "")
        if part_type == TEXT_PART_TYPE:
            text = raw.get("text")
            if isinstance(text, str) and text.strip():
                parts.append({"text": text})
        elif part_type == IMAGE_PART_TYPE:
            data = raw.get("data")
            mime_type = str(raw.get("mime_type") or "image/jpeg")
            if isinstance(data, str) and data.strip():
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": data,
                        }
                    }
                )
    return parts or None