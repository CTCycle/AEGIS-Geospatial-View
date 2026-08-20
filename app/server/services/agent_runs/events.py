from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from server.contracts.events import RunEvent, RunEventCreate, RunEventType, RunEventVisibility
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
        after_sequence: int | None = None,
    ) -> tuple[RunEventSubscription, list[RunEvent]]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        subscription = RunEventSubscription(run_id=run_id, queue=queue)
        async with self._lock:
            self._subscribers[run_id].add(queue)
        # Register before reading replay so an event committed between the
        # cursor lookup and subscription cannot be lost. The generator below
        # rereads by sequence after every notification and deduplicates any
        # overlap between replay and live fan-out.
        replay = self.replay(
            run_id,
            after_sequence=after_sequence,
        )
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
    def replay(
        self,
        run_id: str,
        after_sequence: int | None = None,
    ) -> list[RunEvent]:
        return self.event_repository.list_events(
            run_id,
            after_sequence=after_sequence,
            visibility="user",
        )

    # -------------------------------------------------------------------------
    async def events(
        self,
        run_id: str,
        after_sequence: int | None = None,
    ) -> AsyncGenerator[RunEvent, None]:
        subscription, replay = await self.subscribe(
            run_id,
            after_sequence=after_sequence,
        )
        cursor = after_sequence or 0
        try:
            for event in replay:
                if event.sequence <= cursor:
                    continue
                cursor = event.sequence
                yield event
            while True:
                notification = await subscription.queue.get()
                if notification is None:
                    break
                # A notification is only a wake-up signal. Reading the
                # durable log gives every subscriber the same sequence order,
                # even if concurrent publishers fan out in opposite order.
                for event in self.event_repository.list_events(
                    run_id,
                    after_sequence=cursor,
                    visibility="user",
                ):
                    cursor = event.sequence
                    yield event
        finally:
            await self.unsubscribe(subscription)
