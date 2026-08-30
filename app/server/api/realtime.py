from __future__ import annotations

import ipaddress

from fastapi import APIRouter, HTTPException, Request, WebSocket

from server.common.paths import CONVERSATION_REALTIME_ROUTE, CONVERSATIONS_ROUTER_PREFIX
from server.domain.realtime import REALTIME_SUBPROTOCOL
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.realtime import (
    RealtimeConnection,
    RealtimeConnectionRegistry,
    is_realtime_origin_allowed,
)
from server.services.agent_runs.steering import RunSteeringService

router = APIRouter(prefix=CONVERSATIONS_ROUTER_PREFIX, tags=["realtime"])
metrics_router = APIRouter(prefix="/realtime", tags=["realtime"])


###############################################################################
@router.websocket(CONVERSATION_REALTIME_ROUTE)
async def realtime_socket(
    websocket: WebSocket,
    conversation_id: str,
) -> None:
    if not is_realtime_origin_allowed(websocket):
        await websocket.close(code=1008, reason="origin_not_allowed")
        return
    protocols = {
        item.strip()
        for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if item.strip()
    }
    if REALTIME_SUBPROTOCOL not in protocols:
        await websocket.close(code=1002, reason="unsupported_subprotocol")
        return

    conversation_repository: ConversationRepository = (
        websocket.app.state.conversation_repository
    )
    run_repository: AgentRunRepository = websocket.app.state.run_repository
    lifecycle_service: RunLifecycleService = websocket.app.state.run_lifecycle_service
    steering_service: RunSteeringService = websocket.app.state.run_steering_service
    event_publisher: RunEventPublisher = websocket.app.state.run_event_publisher
    registry: RealtimeConnectionRegistry = websocket.app.state.realtime_connections
    try:
        conversation_repository.verify_conversation_access(conversation_id, None)
    except ValueError, PermissionError:
        await websocket.close(code=4404, reason="conversation_not_found")
        return

    connection = RealtimeConnection(
        websocket,
        conversation_id=conversation_id,
        conversation_repository=conversation_repository,
        run_repository=run_repository,
        lifecycle_service=lifecycle_service,
        steering_service=steering_service,
        event_publisher=event_publisher,
        registry=registry,
        metrics=websocket.app.state.realtime_metrics,
    )
    await connection.run()


###############################################################################
@metrics_router.get("/metrics", include_in_schema=False)
def realtime_metrics(request: Request) -> dict[str, object]:
    """Expose local metrics only to loopback operators."""
    host = request.client.host if request.client is not None else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if not loopback:
        raise HTTPException(status_code=404, detail="Not found")
    return request.app.state.realtime_metrics.snapshot()
