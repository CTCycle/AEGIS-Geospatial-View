from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, AsyncIterator

from server.domain.run_events import RunEvent, RunEventCreate, RunEventType, RunEventVisibility
from server.repositories.agent_run_events import AgentRunEventRepository

###############################################################################
@dataclass(frozen=True)
class RunEventSubscription:
    run_id: str
    queue: asyncio.Queue[RunEvent | None]

###############################################################################
class RunEventPublisher:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        event_repository: AgentRunEventRepository,
        *,
        subscriber_queue_size: int = 100,
    ) -> None:
        self.event_repository = event_repository
        self.subscriber_queue_size = subscriber_queue_size
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent | None]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    async def publish(
        self,
        *,
        conversation_id: str,
        run_id: str,
        run_version: int,
        type: RunEventType,
        payload: dict[str, Any],
        visibility: RunEventVisibility = RunEventVisibility.USER,
    ) -> RunEvent:
        event = self.event_repository.append_event(
            RunEventCreate(
                conversation_id=conversation_id,
                run_id=run_id,
                run_version=run_version,
                type=type,
                visibility=visibility,
                payload=payload,
            )
        )
        if event.visibility == RunEventVisibility.USER:
            await self._fanout(event)
        return event

    # -------------------------------------------------------------------------
    async def _fanout(self, event: RunEvent) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(event.run_id, set()))
        stale: list[asyncio.Queue[RunEvent | None]] = []
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
        for queue in stale:
            await self.unsubscribe(RunEventSubscription(event.run_id, queue))

    # -------------------------------------------------------------------------
    async def subscribe(
        self,
        run_id: str,
        after_event_id: str | None = None,
    ) -> tuple[RunEventSubscription, list[RunEvent]]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        subscription = RunEventSubscription(run_id=run_id, queue=queue)
        replay = self.replay(run_id, after_event_id=after_event_id)
        async with self._lock:
            self._subscribers[run_id].add(queue)
        return subscription, replay

    # -------------------------------------------------------------------------
    async def unsubscribe(self, subscription: RunEventSubscription) -> None:
        async with self._lock:
            queues = self._subscribers.get(subscription.run_id)
            if queues is None:
                return
            queues.discard(subscription.queue)
            if not queues:
                self._subscribers.pop(subscription.run_id, None)

    # -------------------------------------------------------------------------
    def replay(self, run_id: str, after_event_id: str | None = None) -> list[RunEvent]:
        return self.event_repository.list_events(
            run_id,
            after_event_id=after_event_id,
            visibility="user",
        )

    # -------------------------------------------------------------------------
    async def events(
        self,
        run_id: str,
        after_event_id: str | None = None,
    ) -> AsyncIterator[RunEvent]:
        subscription, replay = await self.subscribe(run_id, after_event_id=after_event_id)
        try:
            for event in replay:
                yield event
            while True:
                event = await subscription.queue.get()
                if event is None:
                    break
                yield event
        finally:
            await self.unsubscribe(subscription)
