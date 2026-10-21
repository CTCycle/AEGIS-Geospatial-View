from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Configure application logging before importing modules that may emit startup
# diagnostics (for example, Alembic plugin discovery).
from server.common.logger import logger as _application_logger

from server.api.chat import router as chat_router
from server.api.conversations import router as conversations_router
from server.api.realtime import metrics_router as realtime_metrics_router
from server.api.realtime import router as realtime_router
from server.api.geospatial import router as geospatial_router
from server.api.settings import router as settings_router
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
from server.configurations import DatabaseSettings, ensure_environment_loaded
from server.configurations.database_configuration import (
    load_database_configuration,
)
from server.repositories.runtime_settings import RuntimeSettingsRepository
from server.repositories.database.initializer import initialize_database
from server.repositories.database.sqlite import SQLiteRepository
from server.services.chat.composition import build_chat_runtime
from server.services.chat.conversation_snapshot import ConversationSnapshotService
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.orchestrator import AgentRunOrchestrator
from server.services.agent_runs.render_completion import RenderCompletionService
from server.services.agent_runs.steering import RunSteeringService
from server.services.agent_runs.realtime import RealtimeConnectionRegistry
from server.services.agent_runs.metrics import RealtimeMetrics
from server.services.geospatial.composition import build_geospatial_runtime
from server.services.geospatial.render_capture import RenderCaptureStore
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.services.catalog.startup import seed_reference_catalog
from server.services.startup_validation import run_startup_validations
from server.services.settings.runtime_settings import RuntimeSettingsService
from server.services.database_runtime import (
    DatabaseRuntimeGateMiddleware,
    DatabaseRuntimeManager,
)

###############################################################################
def health_check() -> dict[str, str]:
    return {"status": "ok"}

###############################################################################
def _client_build_available() -> bool:
    return CLIENT_INDEX_FILE_PATH.is_file()

###############################################################################
def _dispose_sqlite_engine(database: object) -> None:
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
@dataclass
class _RuntimeBundle:
    database: SQLiteRepository
    runtime_repository: RuntimeSettingsRepository
    runtime_settings: Any
    settings: Any
    geospatial_runtime: Any
    render_capture_store: RenderCaptureStore
    chat_runtime: Any
    event_repository: AgentRunEventRepository
    run_event_publisher: RunEventPublisher
    run_repository: AgentRunRepository
    conversation_repository: Any
    steering_repository: AgentSteeringRepository
    conversation_snapshot_service: ConversationSnapshotService
    aggregation_service: AggregatedRequestService
    render_completion_service: RenderCompletionService
    run_orchestrator: AgentRunOrchestrator
    run_lifecycle_service: RunLifecycleService
    run_steering_service: RunSteeringService
    realtime_connections: RealtimeConnectionRegistry
    realtime_metrics: RealtimeMetrics
    runtime_settings_service: RuntimeSettingsService


###############################################################################
def _build_runtime_bundle(database_settings: DatabaseSettings) -> _RuntimeBundle:
    database = SQLiteRepository(database_settings)
    try:
        initialize_database(
            database,
            on_ready=lambda: seed_reference_catalog(database),
        )
    except BaseException:
        _dispose_sqlite_engine(database)
        raise

    runtime_repository = RuntimeSettingsRepository(database)
    runtime_app_settings = runtime_repository.get_required()
    settings = runtime_app_settings.to_server_settings(database_settings)
    runtime_settings_service = RuntimeSettingsService(runtime_repository)
    geospatial_runtime = build_geospatial_runtime(database, settings=settings)
    render_capture_store = RenderCaptureStore()
    chat_runtime = build_chat_runtime(
        database,
        geospatial_runtime=geospatial_runtime,
        application_timezone=getattr(
            getattr(settings, "chat", None), "application_timezone", "UTC"
        ),
        execution_settings=getattr(settings, "agent_execution", None),
        render_capture_store=render_capture_store,
    )
    event_repository = AgentRunEventRepository(database)
    run_event_publisher = RunEventPublisher(event_repository)
    run_repository = AgentRunRepository(database, event_repository=event_repository)
    conversation_repository = chat_runtime.conversation_repository
    steering_repository = AgentSteeringRepository(database)
    conversation_snapshot_service = ConversationSnapshotService(
        conversation_repository=conversation_repository,
        history_service=chat_runtime.history_service,
        run_repository=run_repository,
    )
    aggregation_service = AggregatedRequestService()
    render_completion_service = RenderCompletionService(
        run_repository=run_repository,
        event_publisher=run_event_publisher,
        render_ack_timeout_seconds=getattr(
            getattr(settings, "agent_execution", None),
            "render_ack_seconds",
            90.0,
        ),
        resume_mode=True,
        max_render_attempts=getattr(
            getattr(settings, "agent_execution", None),
            "max_render_attempts",
            3,
        ),
    )
    run_orchestrator = AgentRunOrchestrator(
        agent_orchestrator=chat_runtime.agent_orchestrator,
        run_repository=run_repository,
        event_publisher=run_event_publisher,
        conversation_repository=conversation_repository,
        steering_repository=steering_repository,
        render_completion_service=render_completion_service,
        defer_map_completion=True,
    )
    run_lifecycle_service = RunLifecycleService(
        conversation_repository=conversation_repository,
        run_repository=run_repository,
        aggregation_service=aggregation_service,
        event_publisher=run_event_publisher,
        run_orchestrator=run_orchestrator,
        attachment_store=render_capture_store,
    )
    run_steering_service = RunSteeringService(
        run_repository=run_repository,
        steering_repository=steering_repository,
        aggregation_service=aggregation_service,
        event_publisher=run_event_publisher,
        conversation_repository=conversation_repository,
    )
    realtime_connections = RealtimeConnectionRegistry()
    realtime_metrics = RealtimeMetrics()
    return _RuntimeBundle(
        database=database,
        runtime_repository=runtime_repository,
        runtime_settings=runtime_app_settings,
        settings=settings,
        geospatial_runtime=geospatial_runtime,
        render_capture_store=render_capture_store,
        chat_runtime=chat_runtime,
        event_repository=event_repository,
        run_event_publisher=run_event_publisher,
        run_repository=run_repository,
        conversation_repository=conversation_repository,
        steering_repository=steering_repository,
        conversation_snapshot_service=conversation_snapshot_service,
        aggregation_service=aggregation_service,
        render_completion_service=render_completion_service,
        run_orchestrator=run_orchestrator,
        run_lifecycle_service=run_lifecycle_service,
        run_steering_service=run_steering_service,
        realtime_connections=realtime_connections,
        realtime_metrics=realtime_metrics,
        runtime_settings_service=runtime_settings_service,
    )


###############################################################################
def _build_validated_runtime_bundle(
    database_settings: DatabaseSettings,
) -> _RuntimeBundle:
    bundle = _build_runtime_bundle(database_settings)
    try:
        _validate_runtime_bundle(bundle)
    except BaseException:
        _dispose_sqlite_engine(bundle.database)
        raise
    return bundle


###############################################################################
def _publish_runtime_bundle(application: FastAPI, bundle: _RuntimeBundle) -> None:
    application.state.runtime_bundle = bundle
    application.state.database = bundle.database
    application.state.chat_runtime = bundle.chat_runtime
    application.state.geospatial_runtime = bundle.geospatial_runtime
    application.state.run_lifecycle_service = bundle.run_lifecycle_service
    application.state.run_steering_service = bundle.run_steering_service
    application.state.conversation_repository = bundle.conversation_repository
    application.state.conversation_snapshot_service = (
        bundle.conversation_snapshot_service
    )
    application.state.run_repository = bundle.run_repository
    application.state.run_event_publisher = bundle.run_event_publisher
    application.state.render_completion_service = bundle.render_completion_service
    application.state.render_capture_store = bundle.render_capture_store
    application.state.realtime_connections = bundle.realtime_connections
    application.state.realtime_metrics = bundle.realtime_metrics
    application.state.runtime_settings_service = bundle.runtime_settings_service


###############################################################################
async def _activate_runtime_bundle(bundle: _RuntimeBundle) -> None:
    bundle.run_lifecycle_service.resume_active_runs()


###############################################################################
async def _shutdown_runtime_bundle(bundle: _RuntimeBundle) -> None:
    await bundle.realtime_connections.close_all()
    await bundle.run_lifecycle_service.shutdown()
    _dispose_sqlite_engine(bundle.database)


###############################################################################
def _validate_runtime_bundle(bundle: _RuntimeBundle) -> None:
    bundle.chat_runtime.settings_service.validate_persisted_settings()
    run_startup_validations(bundle.geospatial_runtime.catalog_snapshot)


###############################################################################
def _database_busy_reasons(bundle: _RuntimeBundle) -> list[str]:
    reasons: list[str] = []
    if bundle.run_repository.has_active_runs():
        reasons.append("agent runs")
    return reasons

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
    _application_logger.debug("Application logging configured.")
    ensure_environment_loaded()
    configuration = load_database_configuration()
    database_settings = DatabaseSettings(
        database_path=configuration.database_path,
        sqlite_lock_timeout_seconds=configuration.sqlite_lock_timeout_seconds,
        backend=configuration.backend,
    )
    bundle = _build_runtime_bundle(database_settings)
    try:
        _validate_runtime_bundle(bundle)
        _publish_runtime_bundle(application, bundle)
        application.state.database_runtime_manager = DatabaseRuntimeManager(
            configuration=configuration,
            runtime_bundle=bundle,
            build_candidate=_build_validated_runtime_bundle,
            publish_runtime=lambda candidate: _publish_runtime_bundle(
                application, candidate
            ),
            activate_runtime=_activate_runtime_bundle,
            shutdown_runtime=_shutdown_runtime_bundle,
            busy_reasons=_database_busy_reasons,
        )
        await _activate_runtime_bundle(bundle)
        yield
    finally:
        active_bundle = getattr(application.state, "runtime_bundle", bundle)
        await _shutdown_runtime_bundle(active_bundle)

###############################################################################
def create_app() -> FastAPI:
    application = FastAPI(
        title="AEGIS API",
        version=AEGIS_VERSION,
        lifespan=app_lifespan,
    )
    application.add_middleware(
        DatabaseRuntimeGateMiddleware,
        state=application.state,
    )

    application.include_router(chat_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(realtime_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(realtime_metrics_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(geospatial_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(settings_router, prefix=FASTAPI_API_PREFIX)
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
