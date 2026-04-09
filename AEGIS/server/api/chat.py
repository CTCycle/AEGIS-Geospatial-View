from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import StreamingResponse

from AEGIS.server.domain.chat import ChatStreamEvent, ChatTurnRequest, ChatTurnResponse, ModelSettingsResponse, VectorizationResponse
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator
from AEGIS.server.services.chat.model_library import ChatModelLibraryService
from AEGIS.server.services.chat.settings_service import ChatSettingsService
from AEGIS.server.services.llm.ollama import OllamaProvider
from AEGIS.server.services.vector.indexer import VectorIndexer
from AEGIS.server.utils.constants import (
    CHAT_MODELS_ROUTE,
    CHAT_OLLAMA_HEALTH_ROUTE,
    CHAT_OLLAMA_PULL_ROUTE,
    CHAT_OLLAMA_REFRESH_ROUTE,
    CHAT_ROUTER_PREFIX,
    CHAT_SETTINGS_ROUTE,
    CHAT_STREAM_ROUTE,
    CHAT_TURN_ROUTE,
    CHAT_VECTORS_REBUILD_ROUTE,
    CHAT_VECTORS_SYNC_ROUTE,
)

from AEGIS.server.api.search import search_endpoint

router = APIRouter(prefix=CHAT_ROUTER_PREFIX, tags=["chat"])
logger = logging.getLogger(__name__)

settings_repo = ModelSettingsRepository()
settings_service = ChatSettingsService(settings_repo=settings_repo)
model_library_service = ChatModelLibraryService()
vector_indexer = VectorIndexer()
agent_orchestrator = AgentOrchestrator(search_orchestrator=search_endpoint.orchestrator)


@router.post(CHAT_TURN_ROUTE, response_model=ChatTurnResponse, status_code=status.HTTP_200_OK)
async def chat_turn(payload: ChatTurnRequest) -> ChatTurnResponse:
    try:
        vector_indexer.ensure_index_up_to_date()
        return await agent_orchestrator.run_turn(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post(CHAT_STREAM_ROUTE, status_code=status.HTTP_200_OK)
async def chat_stream(payload: ChatTurnRequest):
    def build_tool_status_payload(tool_payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(tool_payload, dict):
            return {"available": False}
        satellite_imagery = tool_payload.get("satellite_imagery")
        map_session = tool_payload.get("map_session")
        overlay_count = 0
        if isinstance(map_session, dict):
            overlays = map_session.get("overlays")
            if isinstance(overlays, list):
                overlay_count = len(overlays)
        return {
            "available": True,
            "execution": tool_payload.get("execution"),
            "has_satellite_imagery": isinstance(satellite_imagery, dict),
            "has_map_session": isinstance(map_session, dict),
            "overlay_count": overlay_count,
        }

    def stream_event(event: ChatStreamEvent) -> str:
        return json.dumps(event.model_dump(mode="json")) + "\n"

    async def event_stream():
        yield stream_event(ChatStreamEvent(event="status", data={"message": "received"}))
        try:
            vector_indexer.ensure_index_up_to_date()
            result = await agent_orchestrator.run_turn(payload)
            for token in result.assistant_message.split():
                yield stream_event(ChatStreamEvent(event="assistant_delta", data={"delta": f"{token} "}))
            if result.tool_payload is not None:
                yield stream_event(
                    ChatStreamEvent(
                        event="tool_status",
                        data=build_tool_status_payload(result.tool_payload),
                    )
                )
            yield stream_event(
                ChatStreamEvent(
                    event="final",
                    data={
                        "session_id": result.session_id,
                        "assistant_message": result.assistant_message,
                        "structured_intent": result.structured_intent,
                        "extracted_state": result.extracted_state,
                        "map_session": result.map_session,
                        "follow_up_required": result.follow_up_required,
                        "fallback_mode": result.fallback_mode,
                    },
                )
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
            yield stream_event(
                ChatStreamEvent(
                    event="error",
                    data={"message": detail, "status": exc.status_code},
                )
            )
        except ValueError as exc:
            yield stream_event(
                ChatStreamEvent(
                    event="error",
                    data={"message": str(exc), "status": status.HTTP_503_SERVICE_UNAVAILABLE},
                )
            )
        except Exception as exc:
            logger.exception("Chat stream failed")
            yield stream_event(
                ChatStreamEvent(
                    event="error",
                    data={"message": str(exc) or "Unexpected server error while streaming response.", "status": 500},
                )
            )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get(CHAT_MODELS_ROUTE, status_code=status.HTTP_200_OK)
def get_models() -> dict[str, list[dict[str, object]]]:
    settings = settings_repo.get_or_create()
    return model_library_service.list_models(ollama_url=settings.ollama_url)


@router.get(CHAT_SETTINGS_ROUTE, response_model=ModelSettingsResponse, status_code=status.HTTP_200_OK)
def get_settings() -> ModelSettingsResponse:
    return settings_service.get_settings()


@router.put(CHAT_SETTINGS_ROUTE, response_model=ModelSettingsResponse, status_code=status.HTTP_200_OK)
def update_settings(payload: dict[str, Any] = Body(default_factory=dict)) -> ModelSettingsResponse:
    return settings_service.update_settings(payload)


@router.post(CHAT_OLLAMA_REFRESH_ROUTE, status_code=status.HTTP_200_OK)
def refresh_ollama_models() -> dict[str, Any]:
    settings = settings_repo.get_or_create()
    provider = OllamaProvider(base_url=settings.ollama_url)
    library_models = provider.list_library_models()
    local_models = provider.list_models()
    return {
        "status": "ok",
        "library_models": [model.name for model in library_models],
        "local_models": [model.name for model in local_models],
    }


@router.post(CHAT_OLLAMA_PULL_ROUTE, status_code=status.HTTP_200_OK)
def pull_ollama_model(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    model_name = payload.get("model")
    if not isinstance(model_name, str) or not model_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is required")
    settings = settings_repo.get_or_create()
    provider = OllamaProvider(base_url=settings.ollama_url)
    return provider.pull_model(model=model_name.strip())


@router.post(CHAT_VECTORS_REBUILD_ROUTE, response_model=VectorizationResponse, status_code=status.HTTP_200_OK)
def rebuild_vectors() -> VectorizationResponse:
    result = vector_indexer.rebuild()
    return VectorizationResponse.model_validate(result)


@router.post(CHAT_VECTORS_SYNC_ROUTE, response_model=VectorizationResponse, status_code=status.HTTP_200_OK)
def sync_vectors() -> VectorizationResponse:
    result = vector_indexer.sync()
    return VectorizationResponse.model_validate(result)


@router.get(CHAT_OLLAMA_HEALTH_ROUTE, status_code=status.HTTP_200_OK)
def check_ollama_health() -> dict[str, Any]:
    settings = settings_repo.get_or_create()
    provider = OllamaProvider(base_url=settings.ollama_url)
    return provider.health_check()
