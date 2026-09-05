"""
Pytest configuration for AEGIS E2E tests.
Provides fixtures for Playwright page objects and API client.
"""

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

import pytest
from server.configurations import DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base

T = TypeVar("T")


###############################################################################
def run_async_in_thread(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine safely when Playwright leaves an event loop active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


###############################################################################
def _pick_first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


###############################################################################
def _normalize_host(raw_host: str | None, default_host: str) -> str:
    host = (raw_host or default_host).strip() or default_host
    if host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host


###############################################################################
def _build_base_url(
    host_env: str,
    port_env: str,
    default_host: str,
    default_port: str,
) -> str:
    host = _normalize_host(os.getenv(host_env), default_host)
    port = os.getenv(port_env, default_port)
    return f"http://{host}:{port}"


FRONTEND_URL_FALLBACK = _build_base_url("UI_HOST", "UI_PORT", "127.0.0.1", "8001")
BACKEND_URL_FALLBACK = _build_base_url(
    "FASTAPI_HOST", "FASTAPI_PORT", "127.0.0.1", "8000"
)

# Base URLs - APP_TEST_* vars are first-class; fall back deterministically.
UI_BASE_URL = _pick_first_non_empty(
    os.getenv("APP_TEST_FRONTEND_URL"),
    os.getenv("UI_BASE_URL"),
    os.getenv("UI_URL"),
    FRONTEND_URL_FALLBACK,
)
API_BASE_URL = _pick_first_non_empty(
    os.getenv("APP_TEST_BACKEND_URL"),
    os.getenv("API_BASE_URL"),
    BACKEND_URL_FALLBACK,
)


###############################################################################
class _SnapshotSaver:
    # -------------------------------------------------------------------------
    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = snapshot_dir

    # -------------------------------------------------------------------------
    def __call__(self, page: Any, name: str) -> Path:
        filename = name if name.lower().endswith(".png") else f"{name}.png"
        target = self.snapshot_dir / filename
        page.screenshot(path=str(target), full_page=True)
        return target


###############################################################################
class _BackendLogTailReader:
    # -------------------------------------------------------------------------
    def __init__(self, backend_log_path: Path) -> None:
        self.backend_log_path = backend_log_path

    # -------------------------------------------------------------------------
    def __call__(self, lines: int = 200) -> str:
        if not self.backend_log_path.exists():
            return ""
        content = self.backend_log_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        return "\n".join(content[-max(1, lines) :])


###############################################################################
@pytest.fixture(scope="session")
def base_url() -> str:
    """Returns the base URL of the UI."""
    return UI_BASE_URL


###############################################################################
@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Returns the base URL of the API."""
    return API_BASE_URL


###############################################################################
@pytest.fixture
def api_context(playwright):
    """
    Creates an API request context for making direct HTTP calls.
    Useful for testing backend endpoints independently of the UI.
    """
    context = playwright.request.new_context(base_url=API_BASE_URL)
    yield context
    context.dispose()


###############################################################################
@pytest.fixture(scope="session")
def artifact_root() -> Path:
    root = Path(
        os.environ.get("APP_TEST_ARTIFACT_ROOT")
        or (Path(__file__).resolve().parents[2] / "assets" / "QA" / "e2e")
    )
    root.mkdir(parents=True, exist_ok=True)
    for child in ("screenshots", "http", "logs", "reports"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


###############################################################################
@pytest.fixture(scope="session")
def backend_log_path(artifact_root: Path) -> Path:
    return artifact_root / "logs" / "backend.log"


###############################################################################
@pytest.fixture(scope="session")
def frontend_log_path(artifact_root: Path) -> Path:
    return artifact_root / "logs" / "frontend.log"


###############################################################################
@pytest.fixture
def snapshot_dir(request: pytest.FixtureRequest, artifact_root: Path) -> Path:
    test_file = request.node.nodeid.split("::", 1)[0].replace("\\", "/").split("/")[-1]
    name = request.node.name.replace("/", "_").replace(" ", "_")
    target = artifact_root / "screenshots" / f"{test_file}__{name}"
    target.mkdir(parents=True, exist_ok=True)
    return target


###############################################################################
@pytest.fixture
def save_snapshot(snapshot_dir: Path) -> _SnapshotSaver:
    return _SnapshotSaver(snapshot_dir)


###############################################################################
@pytest.fixture
def read_backend_log_tail(backend_log_path: Path) -> _BackendLogTailReader:
    return _BackendLogTailReader(backend_log_path)


###############################################################################
@pytest.fixture
def sqlite_backend(tmp_path: Path) -> SQLiteRepository:
    backend = SQLiteRepository(
        DatabaseSettings(
            database_path=str(tmp_path / "database.db"),
        )
    )
    Base.metadata.create_all(backend.engine)
    return backend
