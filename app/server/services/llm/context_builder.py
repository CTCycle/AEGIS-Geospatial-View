from __future__ import annotations

from typing import Any

from server.configurations import get_server_settings


###############################################################################
def build_conversation_context(
    *,
    messages: list[dict[str, Any]],
    extracted_info: str,
    max_messages: int | None = None,
    history_start_index: int = 0,
    current_user_message: str | None = None,
    retrieval_summary: str | None = None,
) -> str:
    cap = max_messages or get_server_settings().chat.max_history_messages
    scoped_messages = messages[max(0, history_start_index) :]
    normalized_messages = list(scoped_messages[-max(1, cap) :])
    parts: list[str] = []
    for message in normalized_messages:
        role = str(message.get("role") or "unknown").strip().lower()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role}: {content}")
    parts.append(f"# current extracted state\n{extracted_info.strip()}")
    if current_user_message:
        parts.append(f"# current user message\n{current_user_message.strip()}")
    if retrieval_summary:
        parts.append(f"# retrieval summary\n{retrieval_summary.strip()}")
    return "\n\n".join(parts)
