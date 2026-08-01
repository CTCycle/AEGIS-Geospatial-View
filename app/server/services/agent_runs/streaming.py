from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from collections.abc import AsyncIterator

from server.domain.run_events import RunEvent, RunEventType
from server.repositories.agent_runs import AgentRunRepository
from server.services.agent_runs.exceptions import RunNotFoundError
from server.services.agent_runs.events import RunEventPublisher


TERMINAL_EVENT_TYPES = {
    RunEventType.COMPLETED,
    RunEventType.CANCELLED,
    RunEventType.ERROR,
}

###############################################################################
class RunEventStreamService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        event_publisher: RunEventPublisher,
        *,
        run_repository: AgentRunRepository,
        keep_alive_seconds: float = 15.0,
    ) -> None:
        self.event_publisher = event_publisher
        self.run_repository = run_repository
        self.keep_alive_seconds = keep_alive_seconds

    # -------------------------------------------------------------------------
    def verify_run_access(self, conversation_id: str, run_id: str) -> None:
        snapshot = self.run_repository.get_run(run_id)
        if snapshot is None or snapshot.conversation_id != conversation_id:
            raise RunNotFoundError("Run not found for conversation.")

    # -------------------------------------------------------------------------
    async def stream_sse(
        self,
        run_id: str,
        *,
        conversation_id: str | None = None,
        after_event_id: str | None = None,
    ) -> AsyncIterator[str]:
        if conversation_id is not None:
            self.verify_run_access(conversation_id, run_id)
        iterator = self.event_publisher.events(run_id, after_event_id=after_event_id)
        pending_next = asyncio.create_task(iterator.__anext__())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {pending_next},
                    timeout=self.keep_alive_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    yield ": keep-alive\n\n"
                    continue
                try:
                    event = pending_next.result()
                except StopAsyncIteration:
                    break
                yield self._sse_frame(event)
                if event.type in TERMINAL_EVENT_TYPES:
                    break
                pending_next = asyncio.create_task(iterator.__anext__())
        except asyncio.CancelledError:
            return
        finally:
            pending_next.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration, RuntimeError):
                await pending_next
            with suppress(RuntimeError):
                await iterator.aclose()

    # -------------------------------------------------------------------------
    @staticmethod
    def _sse_frame(event: RunEvent) -> str:
        return (
            f"id: {event.event_id}\n"
            f"event: {event.type.value}\n"
            f"data: {json.dumps(event.model_dump(mode='json'), default=str)}\n\n"
        )
