from __future__ import annotations

from server.domain.agent.tools import AgentToolCall, AgentToolResult
from server.services.agent.tool_executor import AgentExecutionContext, AgentToolExecutor


class LocationRenderAgent:
    def __init__(self, executor: AgentToolExecutor) -> None:
        self.executor = executor

    async def run(self, call: AgentToolCall, context: AgentExecutionContext) -> AgentToolResult:
        return await self.executor.execute(call, context)
