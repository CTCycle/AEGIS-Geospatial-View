"""Model-facing conversation-history recall handler."""

from __future__ import annotations

import time
from typing import Any, cast

from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.repositories.chat_history import ChatHistoryRepository
from server.services.agent.tool_definitions import SearchConversationHistoryInput

###############################################################################
class HistoryToolHandler:
    """Search original messages in the active conversation only."""

    # -------------------------------------------------------------------------
    def __init__(self, *, repository: ChatHistoryRepository) -> None:
        self.repository = repository

    # -------------------------------------------------------------------------
    async def search_conversation_history(
        self,
        request: SearchConversationHistoryInput,
        state: AgentRunState,
    ) -> ToolResult:
        started = time.perf_counter()
        try:
            page = self.repository.search_conversation_history(
                state.conversation_id,
                request.query,
                before_turn_index=request.before_turn_index,
                cursor=request.cursor,
                limit=request.limit,
            )
        except ValueError as exc:
            return ToolResult(
                call_id="handler-call",
                tool_name="search_conversation_history",
                status="failed",
                summary=str(exc),
                error=ToolExecutionError(
                    error_type="semantic_validation",
                    code=(
                        "invalid_history_cursor"
                        if "cursor" in str(exc).casefold()
                        else "history_unavailable"
                    ),
                    message=str(exc),
                    retryable=False,
                    recovery=(
                        "correct_arguments"
                        if "cursor" in str(exc).casefold()
                        else "terminal"
                    ),
                ),
                metadata=ToolExecutionMetadata(
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000))
                ),
            )

        matches = page.get("messages")
        match_count = (
            len(cast(list[Any], matches)) if isinstance(matches, list) else 0
        )
        status = "success" if match_count else "valid_empty"
        return ToolResult(
            call_id="handler-call",
            tool_name="search_conversation_history",
            status=status,
            summary=(
                f"Found {match_count} matching historical message"
                f"{'s' if match_count != 1 else ''}."
                if match_count
                else "No matching historical messages were found."
            ),
            data=page,
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                result_type="conversation_history",
                result_status=status,
            ),
        )


###############################################################################
__all__ = ["HistoryToolHandler"]
