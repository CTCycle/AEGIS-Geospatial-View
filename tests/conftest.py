"""
Pytest configuration for AEGIS E2E tests.
Provides fixtures for Playwright page objects and API client.
"""

import os

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
