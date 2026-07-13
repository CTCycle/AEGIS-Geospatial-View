from __future__ import annotations

import re
from uuid import uuid4

from server.domain.agent.context import ConversationDirective


###############################################################################
class ConversationInstructionService:
    _DURABLE_MARKERS = re.compile(
        r"\b(for this conversation|from now on|always|unless i request|do not|don't|keep answers?)\b",
        re.IGNORECASE,
    )

    # -------------------------------------------------------------------------
    def apply_user_message(
        self,
        directives: list[ConversationDirective],
        user_text: str,
        source_turn_index: int,
    ) -> list[ConversationDirective]:
        text = " ".join(user_text.strip().split())
        if not text or self._DURABLE_MARKERS.search(text) is None:
            return directives
        normalized = text.casefold()
        result = [item.model_copy(deep=True) for item in directives]
        directive = ConversationDirective(
            directive_id=f"dir_{uuid4().hex}",
            normalized_text=normalized,
            original_user_text=text,
            source_turn_index=source_turn_index,
        )
        for item in result:
            if item.status == "active" and self._conflicts(item.normalized_text, normalized):
                item.status = "superseded"
                item.superseding_directive_id = directive.directive_id
        if not any(item.status == "active" and item.normalized_text == normalized for item in result):
            result.append(directive)
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def active(directives: list[ConversationDirective]) -> list[ConversationDirective]:
        return [item for item in directives if item.status == "active"]

    # -------------------------------------------------------------------------
    @staticmethod
    def _conflicts(existing: str, incoming: str) -> bool:
        topics = ("concise", "brief", "satellite", "traffic", "basemap", "imagery")
        return any(topic in existing and topic in incoming for topic in topics)
