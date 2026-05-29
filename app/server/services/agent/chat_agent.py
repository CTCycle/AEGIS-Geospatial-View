from __future__ import annotations

from server.domain.agent.tools import AgentToolResult


class ChatAgent:
    def render_response(self, *, user_message: str, tool_results: list[AgentToolResult]) -> str:
        if not tool_results:
            return "I can help with that."
        errors = [result.error for result in tool_results if result.error]
        if errors:
            return str(errors[0])
        return "Done. I prepared the requested map operation."
