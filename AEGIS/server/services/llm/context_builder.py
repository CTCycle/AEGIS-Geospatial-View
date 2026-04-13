from __future__ import annotations

from typing import Any

from AEGIS.server.configurations import get_server_settings


def build_conversation_context(
    *,
    messages: list[dict[str, Any]],
    extracted_info: str,
    max_messages: int | None = None,
) -> str:
    cap = max_messages or get_server_settings().chat.max_history_messages
    normalized_messages = list(messages[-max(1, cap) :])
    parts: list[str] = []
    for index, message in enumerate(normalized_messages, start=1):
        content = str(message.get("content") or "").strip()
        parts.append(f"# message {index}\n{content}")
    parts.append(f"# extracted info\n{extracted_info.strip()}")
    return "\n\n".join(parts)
