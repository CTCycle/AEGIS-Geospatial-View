from __future__ import annotations

import os
from typing import Any

from playwright.sync_api import Page

DEFAULT_LANE_PROVIDER = "opencode-go"
DEFAULT_LANE_MODEL = "deepseek-v4.1-flash"


###############################################################################
def selected_model_tool_support_metadata(
    page: Page, api_base_url: str
) -> tuple[bool, str, dict[str, Any]]:
    """Read selected-model tool support without sending a model inference."""
    base_url = api_base_url.rstrip("/")
    settings_response = page.request.get(
        f"{base_url}/api/chat/settings", timeout=10_000
    )
    catalog_response = page.request.get(f"{base_url}/api/chat/models", timeout=10_000)
    try:
        settings = settings_response.json()
    except (TypeError, ValueError):
        settings = {}
    try:
        catalog = catalog_response.json()
    except (TypeError, ValueError):
        catalog = {}

    settings = settings if isinstance(settings, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    provider = settings.get("agent_model_provider")
    model_name = settings.get("agent_model_name")
    models = [
        model
        for collection in (catalog.get("cloud"), catalog.get("local"))
        if isinstance(collection, list)
        for model in collection
        if isinstance(model, dict)
    ]
    selected = next(
        (
            model
            for model in models
            if model.get("provider") == provider and model.get("name") == model_name
        ),
        None,
    )
    supports_tools = selected.get("supports_tools") if selected else None
    evidence: dict[str, Any] = {
        "settings_http_status": settings_response.status,
        "catalog_http_status": catalog_response.status,
        "provider": provider if isinstance(provider, str) else None,
        "model": model_name if isinstance(model_name, str) else None,
        "supports_tools": supports_tools if isinstance(supports_tools, bool) else None,
        "tool_support_source": (
            selected.get("tool_support_source") if selected else None
        ),
        "protocol": selected.get("protocol") if selected else None,
    }

    if settings_response.status != 200 or catalog_response.status != 200:
        return (
            False,
            "Selected model capability metadata could not be loaded.",
            evidence,
        )
    if selected is None:
        return False, "Selected model is missing from the current catalog.", evidence
    if supports_tools is False:
        return (
            False,
            "Selected model metadata reports no tool-calling support.",
            evidence,
        )
    if supports_tools is not True:
        return (
            False,
            "Selected model tool-calling support is not verified by metadata.",
            evidence,
        )
    return True, "", evidence


###############################################################################
def exact_lane_tool_support_metadata(
    page: Page, api_base_url: str
) -> tuple[bool, str, dict[str, Any]]:
    """Require the configured validation lane, ``APP_TEST_LANE_PROVIDER`` / ``APP_TEST_LANE_MODEL``."""
    provider = os.environ.get("APP_TEST_LANE_PROVIDER", DEFAULT_LANE_PROVIDER).strip()
    model = os.environ.get("APP_TEST_LANE_MODEL", DEFAULT_LANE_MODEL).strip()
    ready, reason, evidence = selected_model_tool_support_metadata(page, api_base_url)
    if ready and (evidence["provider"] != provider or evidence["model"] != model):
        return False, f"Live validation requires {provider} / {model}.", evidence
    return ready, reason, evidence
