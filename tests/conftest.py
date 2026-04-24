"""
Pytest configuration for AEGIS E2E tests.
Provides fixtures for Playwright page objects and API client.
"""

import os
from pathlib import Path

import pytest


def _pick_first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _normalize_host(raw_host: str | None, default_host: str) -> str:
    host = (raw_host or default_host).strip() or default_host
    if host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host


def _build_base_url(
    host_env: str,
    port_env: str,
    default_host: str,
    default_port: str,
) -> str:
    host = _normalize_host(os.getenv(host_env), default_host)
    port = os.getenv(port_env, default_port)
    return f"http://{host}:{port}"


FRONTEND_URL_FALLBACK = _build_base_url("UI_HOST", "UI_PORT", "127.0.0.1", "7861")
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


@pytest.fixture(scope="session")
def base_url() -> str:
    """Returns the base URL of the UI."""
    return UI_BASE_URL


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Returns the base URL of the API."""
    return API_BASE_URL


@pytest.fixture
def api_context(playwright):
    """
    Creates an API request context for making direct HTTP calls.
    Useful for testing backend endpoints independently of the UI.
    """
    context = playwright.request.new_context(base_url=API_BASE_URL)
    yield context
    context.dispose()


@pytest.fixture(scope="session")
def artifact_root() -> Path:
    root = Path(__file__).parent / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    for child in ("screenshots", "http", "logs", "reports"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="session")
def backend_log_path(artifact_root: Path) -> Path:
    return artifact_root / "logs" / "backend.log"


@pytest.fixture(scope="session")
def frontend_log_path(artifact_root: Path) -> Path:
    return artifact_root / "logs" / "frontend.log"


@pytest.fixture
def snapshot_dir(request: pytest.FixtureRequest, artifact_root: Path) -> Path:
    test_file = request.node.nodeid.split("::", 1)[0].replace("\\", "/").split("/")[-1]
    name = request.node.name.replace("/", "_").replace(" ", "_")
    target = artifact_root / "screenshots" / f"{test_file}__{name}"
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture
def save_snapshot(snapshot_dir: Path):
    def _save(page, name: str) -> Path:  # noqa: ANN001
        filename = name if name.lower().endswith(".png") else f"{name}.png"
        target = snapshot_dir / filename
        page.screenshot(path=str(target), full_page=True)
        return target

    return _save


@pytest.fixture
def read_backend_log_tail(backend_log_path: Path):
    def _read(lines: int = 200) -> str:
        if not backend_log_path.exists():
            return ""
        content = backend_log_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        return "\n".join(content[-max(1, lines) :])

    return _read
