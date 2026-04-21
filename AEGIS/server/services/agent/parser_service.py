from __future__ import annotations

from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    TurnParseResult,
)
from AEGIS.server.services.agent.parser_rules import (
    detect_deictic_references,
    detect_disallowed_patterns,
    detect_location_signals,
    detect_temporal_signals,
    merge_symbolic_and_model_output,
)


class ParserService:
    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
    ) -> TurnParseResult:
        location_signals = detect_location_signals(user_message)
        temporal_signal = detect_temporal_signals(user_message)
        disallowed = detect_disallowed_patterns(user_message)
        deictic = detect_deictic_references(user_message)
        task_class, normalized_intent = merge_symbolic_and_model_output(user_message)

        ambiguities: list[str] = []
        if not location_signals and normalized_intent.requires_location:
            ambiguities.append("missing_location")
        if deictic and not memory_snapshot.get("active_location"):
            ambiguities.append("deictic_without_memory")

        confidence = 0.55
        if location_signals:
            confidence += 0.25
        if ambiguities:
            confidence -= 0.2
        if disallowed:
            confidence -= 0.2

        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=conversation_messages[-8:],
                memory_snapshot=memory_snapshot,
            ),
            task_class=task_class,
            location_signals=location_signals,
            normalized_intent=normalized_intent,
            temporal_signal=temporal_signal,
            ambiguities=ambiguities,
            disallowed_patterns=disallowed,
            parser_confidence=max(0.0, min(1.0, confidence)),
        )
