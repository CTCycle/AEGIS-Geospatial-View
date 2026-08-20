from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.api.chat import router as chat_router
from server.api.conversations import router as conversations_router
from server.api.realtime import metrics_router as realtime_metrics_router
from server.api.realtime import router as realtime_router
from server.api.geospatial import router as geospatial_router
from server.api.jobs import router as jobs_router
from server.common.constants import AEGIS_VERSION
from server.common.paths import (
    CLIENT_ASSETS_PATH,
    CLIENT_DIST_PATH,
    CLIENT_INDEX_FILE_PATH,
    FASTAPI_API_PREFIX,
    FASTAPI_ASSETS_ENDPOINT,
    FASTAPI_DOCS_ENDPOINT,
    FASTAPI_ROOT_ENDPOINT,
    FASTAPI_SPA_FALLBACK_ENDPOINT,
)
from server.configurations import get_server_settings
from server.repositories.database import build_database_backend
from server.repositories.database.initializer import initialize_database
from server.services.chat.composition import build_chat_runtime
from server.services.chat.streaming import ChatStreamingService
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.orchestrator import AgentRunOrchestrator
from server.services.agent_runs.steering import RunSteeringService
from server.services.agent_runs.realtime import RealtimeConnectionRegistry
from server.services.agent_runs.metrics import RealtimeMetrics
from server.services.geospatial.composition import build_geospatial_runtime
from server.services.jobs import BackgroundJobService
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.credentials import CredentialRepository
from server.services.search.composition import build_search_runtime
from server.services.startup_validation import run_startup_validations

###############################################################################
def health_check() -> dict[str, str]:
    return {"status": "ok"}

###############################################################################
def _client_build_available() -> bool:
    return CLIENT_INDEX_FILE_PATH.is_file()


def _dispose_database_engine(database: object) -> None:
    engine = getattr(database, "engine", None)
    dispose = getattr(engine, "dispose", None)
    if callable(dispose):
        dispose()

###############################################################################
def _resolve_client_file(full_path: str) -> Path | None:
    client_root = CLIENT_DIST_PATH.resolve()
    requested_path = (client_root / full_path).resolve()

    if not requested_path.is_relative_to(client_root):
        return None

    if requested_path.is_file():
        return requested_path

    return None

###############################################################################
def serve_client_root() -> FileResponse:
    return FileResponse(CLIENT_INDEX_FILE_PATH)

###############################################################################
def serve_client_path(full_path: str) -> FileResponse:
    client_file = _resolve_client_file(full_path)
    if client_file is not None:
        return FileResponse(client_file)
    return FileResponse(CLIENT_INDEX_FILE_PATH)

###############################################################################
def redirect_root_to_docs() -> RedirectResponse:
    return RedirectResponse(FASTAPI_DOCS_ENDPOINT)

###############################################################################
@asynccontextmanager
async def app_lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_server_settings()
    database = build_database_backend(settings.database)

    try:
        initialize_database(database)
    except BaseException:
        _dispose_database_engine(database)
        raise

    search_runtime = build_search_runtime()
    chat_runtime = build_chat_runtime(search_runtime.search_orchestrator, database)
    geospatial_runtime = build_geospatial_runtime(database)
    chat_streaming_service = ChatStreamingService(chat_runtime.agent_orchestrator)
    run_event_publisher = RunEventPublisher(AgentRunEventRepository(database))
    run_repository = AgentRunRepository(database)
    conversation_repository = chat_runtime.conversation_repository
    aggregation_service = AggregatedRequestService()
    run_orchestrator = AgentRunOrchestrator(
        agent_orchestrator=chat_runtime.agent_orchestrator,
        run_repository=run_repository,
        event_publisher=run_event_publisher,
        conversation_repository=conversation_repository,
        steering_repository=AgentSteeringRepository(database),
    )
    run_lifecycle_service = RunLifecycleService(
        conversation_repository=conversation_repository,
        run_repository=run_repository,
        aggregation_service=aggregation_service,
        event_publisher=run_event_publisher,
        run_orchestrator=run_orchestrator,
    )
    run_steering_service = RunSteeringService(
        run_repository=run_repository,
        steering_repository=AgentSteeringRepository(database),
        aggregation_service=aggregation_service,
        event_publisher=run_event_publisher,
        conversation_repository=conversation_repository,
        task_state_service=getattr(
            chat_runtime.agent_orchestrator,
            "task_state_service",
            None,
        ),
    )
    realtime_connections = RealtimeConnectionRegistry()
    realtime_metrics = RealtimeMetrics()
    job_service = BackgroundJobService(
        chat_streaming_service=chat_streaming_service,
        polling_interval=settings.jobs.polling_interval,
    )
    application.state.search_runtime = search_runtime
    application.state.chat_runtime = chat_runtime
    application.state.geospatial_runtime = geospatial_runtime
    application.state.chat_streaming_service = chat_streaming_service
    application.state.run_lifecycle_service = run_lifecycle_service
    application.state.run_steering_service = run_steering_service
    application.state.conversation_repository = conversation_repository
    application.state.run_repository = run_repository
    application.state.run_event_publisher = run_event_publisher
    application.state.realtime_connections = realtime_connections
    application.state.realtime_metrics = realtime_metrics
    application.state.job_service = job_service

    try:
        job_service.start()
        chat_runtime.settings_service.get_settings()
        run_startup_validations(CredentialRepository(database))
        yield
    finally:
        await realtime_connections.close_all()
        job_service.stop()
        await run_lifecycle_service.shutdown()
        _dispose_database_engine(database)

###############################################################################
def create_app() -> FastAPI:
    application = FastAPI(
        title="AEGIS API",
        version=AEGIS_VERSION,
        lifespan=app_lifespan,
    )

    application.include_router(chat_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(realtime_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(realtime_metrics_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(jobs_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(geospatial_router, prefix=FASTAPI_API_PREFIX)
    application.add_api_route(
        f"{FASTAPI_API_PREFIX}/health",
        health_check,
        methods=["GET"],
        include_in_schema=False,
    )

    if _client_build_available():
        if CLIENT_ASSETS_PATH.is_dir():
            application.mount(
                FASTAPI_ASSETS_ENDPOINT,
                StaticFiles(directory=CLIENT_ASSETS_PATH),
                name="assets",
            )
        application.add_api_route(
            FASTAPI_ROOT_ENDPOINT,
            serve_client_root,
            methods=["GET"],
            include_in_schema=False,
        )
        application.add_api_route(
            FASTAPI_SPA_FALLBACK_ENDPOINT,
            serve_client_path,
            methods=["GET"],
            include_in_schema=False,
        )

    else:
        application.add_api_route(
            FASTAPI_ROOT_ENDPOINT,
            redirect_root_to_docs,
            methods=["GET"],
            include_in_schema=False,
        )

    return application


app = create_app()
