from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, expect
from server.configurations.settings import AppSettings

from tests.e2e.helpers.chat_stub_payloads import (
    chat_completion_map_payload,
    chat_completion_text_payload,
    geospatial_catalog_payload,
    model_catalog_payload,
    selected_agent_settings_payload,
)
from tests.e2e.helpers.realtime_stub import register_realtime_stub

PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)
SETTINGS_UI_QA_DIR = Path(__file__).resolve().parents[3] / "assets" / "QA" / "settings-ui"
T1_10_SETTINGS_QA_DIR = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "QA"
    / "tier1-validation-develop-20260923"
    / "T1-10"
)

###############################################################################
def settings_provider_account_setup_payload() -> dict[str, Any]:
    return {
        "providers": [
            {
                "provider_id": "tomtom",
                "name": "TomTom",
                "requires_credentials": True,
                "auth_mode": "api_key",
                "docs_url": "https://developer.tomtom.com/",
                "configured": False,
                "instructions": [
                    "Create or sign in to a TomTom developer account.",
                    "Copy the browser key into AEGIS after it is generated.",
                ],
                "automation": {
                    "support": "manual_only",
                    "signup_url": "https://developer.tomtom.com/user/register",
                    "developer_portal_url": "https://developer.tomtom.com/",
                    "docs_url": "https://developer.tomtom.com/",
                    "required_fields": [
                        {
                            "key": "email",
                            "label": "Email address",
                            "field_type": "email",
                            "required": True,
                            "sensitive": False,
                            "help_text": "Use an address you control.",
                        }
                    ],
                    "user_action_notes": [
                        "Open the provider portal and complete the account steps in your browser.",
                        "Return here and paste the generated API key.",
                    ],
                    "safety_notes": [
                        "AEGIS never receives provider passwords or submits payment details.",
                    ],
                    "experimental": False,
                    "experimental_label": "Manual setup guidance",
                },
                "credential_storage_key": "tomtom",
                "credential_label": "TomTom API key",
                "key_format_hint": "Paste TomTom API key",
                "validation_supported": False,
            }
        ]
    }

###############################################################################
def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

###############################################################################
def _request_json(route: Route) -> dict[str, Any]:
    raw_post_data = getattr(route.request, "post_data", None)
    if callable(raw_post_data):
        raw_post_data = raw_post_data()
    if isinstance(raw_post_data, str) and raw_post_data.strip():
        try:
            payload = json.loads(raw_post_data)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
    try:
        payload = route.request.post_data_json()
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}

###############################################################################
def _setup_stub_harness(
    page: Page,
    *,
    settings_payload: dict[str, Any] | None = None,
    models_payload: dict[str, Any] | None = None,
    turn_payload_factory: Callable[[str], dict[str, Any]] | None = None,
    patch_payloads: list[dict[str, Any]] | None = None,
    settings_responses: list[dict[str, Any]] | None = None,
    settings_patch_failure: bool = False,
) -> list[dict[str, Any]]:
    page.add_init_script(
        """
        () => {
          window.sessionStorage.clear();
          window.localStorage.clear();
        }
        """
    )

    active_settings = dict(settings_payload or selected_agent_settings_payload())
    active_models = models_payload or model_catalog_payload()
    captured_patch_payloads = patch_payloads if patch_payloads is not None else []
    captured_settings_responses = settings_responses if settings_responses is not None else []

    def handle_settings(route: Route) -> None:
        method = route.request.method.upper()
        if method == "GET":
            _json_ok(route, active_settings)
            return
        if method == "PATCH":
            payload = _request_json(route)
            if payload:
                captured_patch_payloads.append(payload)
            if settings_patch_failure:
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body=json.dumps({"detail": "Synthetic credential update failure."}),
                )
                return
            active_settings.update(
                {key: value for key, value in payload.items() if key != "credentials"}
            )
            if "credentials" in payload:
                saved_credentials = dict(active_settings.get("credentials", {}))
                saved_health = dict(active_settings.get("credential_health", {}))
                for provider, provider_updates in payload["credentials"].items():
                    provider_credentials = dict(saved_credentials.get(provider, {}))
                    provider_health = dict(saved_health.get(provider, {}))
                    for label, value in provider_updates.items():
                        if value:
                            provider_credentials[label] = True
                            provider_health[label] = (
                                "healthy"
                                if provider
                                in {"openai", "google", "deepseek", "opencode", "opencode-go"}
                                else "stored"
                            )
                        else:
                            provider_credentials.pop(label, None)
                            provider_health.pop(label, None)
                    if provider_credentials:
                        saved_credentials[provider] = provider_credentials
                    else:
                        saved_credentials.pop(provider, None)
                    if provider_health:
                        saved_health[provider] = provider_health
                    else:
                        saved_health.pop(provider, None)
                active_settings["credentials"] = saved_credentials
                active_settings["credential_health"] = saved_health
            if "agent_model_provider" in payload or "agent_model_name" in payload:
                active_settings["selected_model_context"] = {
                    "provider": active_settings["agent_model_provider"],
                    "model": active_settings["agent_model_name"],
                    "context_window_tokens": None,
                    "maximum_output_tokens": None,
                    "context_profile_source": "unknown",
                    "context_metadata_authority": "unknown",
                }
            captured_settings_responses.append(dict(active_settings))
            _json_ok(route, active_settings)
            return
        route.fulfill(
            status=405,
            content_type="application/json",
            body=json.dumps({"detail": "Method not allowed"}),
        )

    def handle_create_conversation(route: Route) -> None:
        _json_ok(route, {"conversation_id": "conversation-e2e", "title": "E2E"})

    page.route(re.compile(r".*/api/chat/settings.*"), handle_settings)
    page.route(
        re.compile(r".*/api/chat/models.*"),
        lambda route: _json_ok(route, active_models),
    )
    page.route(
        re.compile(r".*/api/geospatial/capabilities.*"),
        lambda route: _json_ok(route, geospatial_catalog_payload()),
    )
    page.route(
        re.compile(r".*/api/geospatial/providers/account-setup$"),
        lambda route: _json_ok(route, settings_provider_account_setup_payload()),
    )
    page.route(re.compile(r".*/api/conversations$"), handle_create_conversation)
    page.route(
        re.compile(r".*/api/geospatial/tiles/osm_default/\d+/\d+/\d+\.png(?:\?.*)?$"),
        lambda route: route.fulfill(
            status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT
        ),
    )
    register_realtime_stub(
        page,
        lambda message, _run_number: (
            turn_payload_factory(message)
            if turn_payload_factory is not None
            else chat_completion_map_payload(9001, "Search executed successfully.")
        ),
    )
    return captured_patch_payloads

###############################################################################
def test_settings_layout_has_no_overlap_at_minimum_desktop_width(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)
    page.set_viewport_size({"width": 1024, "height": 700})

    page.goto(f"{base_url.rstrip('/')}/settings?mode=cloud")

    expect(page.locator(".model-card").first).to_be_visible(timeout=15000)
    expect(
        page.get_by_role("complementary", name="Selected agent model")
    ).to_be_visible(timeout=15000)
    expect(page.get_by_role("button", name="Test selected model")).to_be_visible(
        timeout=5000
    )

    layout_metrics = page.evaluate(
        """
        () => {
          const left = document.querySelector('.settings-page__left-column');
          const right = document.querySelector('.settings-page__right-column');
          const asRect = (el) => {
            const r = el.getBoundingClientRect();
            return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
          };
          return {
            leftRect: left ? asRect(left) : null,
            rightRect: right ? asRect(right) : null,
            bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          };
        }
        """
    )

    assert layout_metrics["leftRect"] is not None
    assert layout_metrics["rightRect"] is not None
    assert layout_metrics["bodyOverflow"] <= 1
    left = layout_metrics["leftRect"]
    right = layout_metrics["rightRect"]
    assert (
        left["right"] <= right["left"] + 1
        or right["right"] <= left["left"] + 1
        or left["bottom"] <= right["top"] + 1
        or right["bottom"] <= left["top"] + 1
    )

###############################################################################
def test_settings_provider_surfaces_and_setup_modal_are_responsive(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)

    for width, height, expected_columns in ((1366, 768, 1), (1024, 700, 1)):
        page.set_viewport_size({"width": width, "height": height})
        page.goto(f"{base_url.rstrip('/')}/settings?tab=model-providers")

        provider_grid = page.locator(".settings-provider-list")
        expect(provider_grid).to_be_visible(timeout=15000)
        expect(provider_grid.locator(".settings-provider-card").first).to_be_visible(
            timeout=15000
        )

        layout_metrics = page.evaluate(
            """
            () => {
              const grid = document.querySelector('.settings-provider-list');
              const gridRect = grid?.getBoundingClientRect();
              const rect = (element) => {
                const value = element.getBoundingClientRect();
                return { left: value.left, right: value.right, top: value.top, bottom: value.bottom };
              };
              return {
                bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                columnCount: grid ? getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/).length : 0,
                gridRect: gridRect ? rect(grid) : null,
                cards: [...document.querySelectorAll('.settings-provider-list .settings-provider-card')].map((card) => ({
                  card: rect(card),
                  input: card.querySelector('input') ? rect(card.querySelector('input')) : null,
                  actions: card.querySelector('.settings-actions') ? rect(card.querySelector('.settings-actions')) : null,
                })),
              };
            }
            """
        )

        assert layout_metrics["bodyOverflow"] <= 1
        assert layout_metrics["columnCount"] == expected_columns
        grid_rect = layout_metrics["gridRect"]
        assert grid_rect is not None
        for card in layout_metrics["cards"]:
            assert card["card"]["left"] >= grid_rect["left"] - 1
            assert card["card"]["right"] <= grid_rect["right"] + 1
            if card["input"] is not None:
                assert card["input"]["right"] <= card["card"]["right"] + 1
            if card["actions"] is not None:
                assert card["actions"]["right"] <= card["card"]["right"] + 1

        SETTINGS_UI_QA_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(SETTINGS_UI_QA_DIR / f"model-providers-{width}.png"),
            full_page=True,
        )

        page.get_by_role("button", name="Geospatial Access").click()
        geospatial_card = page.locator(".settings-provider-list .settings-provider-card").first
        expect(geospatial_card).to_be_visible(timeout=15000)
        page.get_by_role("button", name="Get API key").click()
        dialog = page.get_by_role("dialog", name="API key setup for TomTom")
        expect(dialog).to_be_visible(timeout=5000)

        modal_metrics = dialog.evaluate(
            """
            (element) => {
              const dialogRect = element.getBoundingClientRect();
              const content = element.querySelector('.provider-signup-modal');
              const actions = element.querySelector('.settings-actions');
              const rect = (value) => {
                const result = value.getBoundingClientRect();
                return { left: result.left, right: result.right, top: result.top, bottom: result.bottom };
              };
              return {
                dialog: rect(element),
                contentOverflow: content ? content.scrollWidth - content.clientWidth : 0,
                actions: actions ? rect(actions) : null,
                overflowY: getComputedStyle(element).overflowY,
              };
            }
            """
        )

        assert modal_metrics["dialog"]["left"] >= -1
        assert modal_metrics["dialog"]["right"] <= width + 1
        assert modal_metrics["dialog"]["top"] >= -1
        assert modal_metrics["dialog"]["bottom"] <= height + 1
        assert modal_metrics["contentOverflow"] <= 1
        assert modal_metrics["actions"] is not None
        assert modal_metrics["actions"]["right"] <= modal_metrics["dialog"]["right"] + 1
        assert modal_metrics["overflowY"] in {"auto", "scroll"}

        page.screenshot(
            path=str(SETTINGS_UI_QA_DIR / f"geospatial-setup-modal-{width}.png"),
            full_page=True,
        )

        page.get_by_role("button", name="Cancel guided setup").click()
        expect(dialog).to_be_hidden(timeout=5000)

###############################################################################
def test_model_card_selects_the_single_agent_model(page: Page, base_url: str) -> None:
    patch_payloads: list[dict[str, Any]] = []
    settings_responses: list[dict[str, Any]] = []
    expected_initial = selected_agent_settings_payload()
    _setup_stub_harness(
        page,
        settings_payload=expected_initial,
        patch_payloads=patch_payloads,
        settings_responses=settings_responses,
    )
    page.set_viewport_size({"width": 1366, "height": 768})

    page.goto(f"{base_url.rstrip('/')}/settings")

    model_card = (
        page.locator("article.model-card")
        .filter(has=page.get_by_role("heading", name="gpt-5-mini"))
        .first
    )
    expect(model_card).to_be_visible(timeout=15000)
    selection_button = model_card.get_by_role(
        "button", name="Select as agent model: gpt-5-mini"
    )
    selection_button.focus()
    def settings_patch(response: Any) -> bool:
        return (
            response.request.method == "PATCH"
            and response.url.endswith("/api/chat/settings")
        )

    with page.expect_response(settings_patch) as first_selection_response:
        page.keyboard.press("Enter")
    first_response = first_selection_response.value.json()
    assert first_response["agent_model_name"] == "gpt-5-mini"
    assert first_response["selected_model_context"]["model"] == "gpt-5-mini"

    selected_button = model_card.get_by_role(
        "button", name="Selected agent model: gpt-5-mini"
    )
    expect(selected_button).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".settings-page__status")).to_have_text(
        "Selected gpt-5-mini as agent model"
    )
    selected_button.focus()
    with page.expect_response(settings_patch) as second_selection_response:
        page.keyboard.press("Space")
    second_response = second_selection_response.value.json()
    assert second_response["agent_model_name"] == "gpt-5-mini"
    assert second_response["selected_model_context"]["model"] == "gpt-5-mini"
    expect(page.locator(".settings-page__status")).to_have_text(
        "Selected gpt-5-mini as agent model"
    )
    summary = page.get_by_role("complementary", name="Selected agent model")
    expect(summary.get_by_role("heading", name="gpt-5-mini")).to_be_visible()
    probe_button = page.get_by_role("button", name="Test selected model")
    expect(probe_button).to_be_visible()
    selected_panel_metrics = page.evaluate(
        """
        () => {
          const column = document.querySelector('.settings-page__right-column');
          const probe = document.querySelector('.settings-page__probe');
          const summary = document.querySelector('.selected-model-summary');
          const rect = (element) => {
            const value = element.getBoundingClientRect();
            return { top: value.top, bottom: value.bottom, height: value.height };
          };
          return {
            column: column ? rect(column) : null,
            probe: probe ? rect(probe) : null,
            summary: summary ? rect(summary) : null,
            summaryScrollHeight: summary?.scrollHeight ?? null,
            summaryClientHeight: summary?.clientHeight ?? null,
          };
        }
        """
    )
    assert selected_panel_metrics["column"] is not None
    assert selected_panel_metrics["probe"] is not None
    assert selected_panel_metrics["probe"]["bottom"] <= selected_panel_metrics["column"]["bottom"] + 1, selected_panel_metrics
    assert selected_panel_metrics["summaryScrollHeight"] >= selected_panel_metrics["summaryClientHeight"]
    T1_10_SETTINGS_QA_DIR.joinpath("screenshots").mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(T1_10_SETTINGS_QA_DIR / "screenshots" / "models-selected-model.png"),
        full_page=True,
    )
    assert patch_payloads, "Expected PATCH /api/chat/settings payload to be captured."
    payload = patch_payloads[-1]
    if "agent_model_provider" not in payload:
        matching_payloads = [
            item for item in patch_payloads if "agent_model_provider" in item
        ]
        assert matching_payloads, f"No model settings payload captured: {patch_payloads}"
        payload = matching_payloads[-1]

    assert payload["agent_model_provider"] == "openai"
    assert payload["agent_model_name"] == "gpt-5-mini"
    assert "ollama_url" not in payload
    assert "openai_base_url" not in payload
    assert "google_base_url" not in payload
    assert set(payload["credentials"].keys()) == set(
        expected_initial["credentials"].keys()
    )
    assert payload["active_provider_mode"] == "cloud"
    assert "credential_health" not in payload
    assert all("api_key" not in values for values in payload["credentials"].values())
    assert settings_responses, "Expected a Settings response after selecting the model."
    for response in settings_responses:
        assert response["agent_model_provider"] == "openai"
        assert response["agent_model_name"] == "gpt-5-mini"
        assert response["selected_model_context"]["model"] == "gpt-5-mini"


###############################################################################
def test_model_provider_unreadable_key_and_failed_updates_are_safe(
    page: Page, base_url: str
) -> None:
    settings_payload = selected_agent_settings_payload()
    settings_payload["credentials"] = {"openai": {"api_key": True}}
    settings_payload["credential_health"] = {"openai": {"api_key": "unreadable"}}
    patch_payloads: list[dict[str, Any]] = []
    _setup_stub_harness(
        page,
        settings_payload=settings_payload,
        patch_payloads=patch_payloads,
        settings_patch_failure=True,
    )
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{base_url.rstrip('/')}/settings")
    page.get_by_role("button", name="Model Providers").click()

    card = page.locator(".settings-provider-card").filter(
        has=page.get_by_role("heading", name="OpenAI", exact=True)
    )
    key_input = card.get_by_label("OpenAI API key")
    expect(key_input).to_be_visible()
    expect(key_input).to_have_attribute("type", "password")
    expect(key_input).to_have_value("")
    expect(card.get_by_text("Saved key cannot be read")).to_be_visible()
    expect(
        card.get_by_text("Saved key cannot be decrypted. Re-enter the key.")
    ).to_be_visible()

    card.get_by_role("button", name="Save key").click()
    expect(
        page.get_by_text("Enter a OpenAI API key before saving.", exact=True)
    ).to_be_visible()
    key_input.fill("not-a-valid-key")
    card.get_by_role("button", name="Save key").click()
    expect(
        card.get_by_text(
            'OpenAI key must start with "sk-" and include a valid key body.',
            exact=True,
        )
    ).to_be_visible()
    assert patch_payloads == []

    card.get_by_role("button", name="Clear saved key").click()
    expect(page.get_by_text("Synthetic credential update failure.", exact=True)).to_be_visible()
    expect(page.get_by_text("OpenAI key cleared.", exact=True)).to_have_count(0)
    expect(card.get_by_text("Saved key cannot be read")).to_be_visible()
    assert len(patch_payloads) == 1

    fixture_key = "sk-fixturekey12345"
    key_input.fill(fixture_key)
    card.get_by_role("button", name="Save key").click()
    expect(page.get_by_text("Synthetic credential update failure.", exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            "OpenAI key saved. Provider access has not been validated.", exact=True
        )
    ).to_have_count(0)
    expect(key_input).to_have_value(fixture_key)
    expect(key_input).to_have_attribute("type", "password")
    expect(page.locator("body")).not_to_contain_text(fixture_key)
    expect(card.get_by_text("Saved key cannot be read")).to_be_visible()
    assert len(patch_payloads) == 2

    screenshots = T1_10_SETTINGS_QA_DIR / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshots / "model-provider-update-failure.png"), full_page=True)


###############################################################################
def test_model_provider_credential_safe_save_clear_and_reload(
    page: Page, base_url: str
) -> None:
    settings_payload = selected_agent_settings_payload()
    settings_payload["credentials"] = {}
    settings_payload["credential_health"] = {}
    patch_payloads: list[dict[str, Any]] = []
    _setup_stub_harness(
        page, settings_payload=settings_payload, patch_payloads=patch_payloads
    )
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{base_url.rstrip('/')}/settings")
    page.get_by_role("button", name="Model Providers").click()

    card = page.locator(".settings-provider-card").filter(
        has=page.get_by_role("heading", name="OpenAI", exact=True)
    )
    key_input = card.get_by_label("OpenAI API key")
    clear_button = card.get_by_role("button", name="Clear saved key")
    expect(key_input).to_have_attribute("type", "password")
    expect(key_input).to_have_value("")
    expect(clear_button).to_be_disabled()

    fixture_key = "sk-fixturekey12345"
    key_input.fill(fixture_key)
    card.get_by_role("button", name="Save key").click()
    expect(
        page.get_by_text(
            "OpenAI key saved. Provider access has not been validated.", exact=True
        )
    ).to_be_visible()
    expect(key_input).to_have_value("")
    expect(card.get_by_text("Saved key is readable.", exact=True)).to_be_visible()
    expect(clear_button).to_be_enabled()
    expect(page.locator("body")).not_to_contain_text(fixture_key)
    assert len(patch_payloads) == 1

    screenshots = T1_10_SETTINGS_QA_DIR / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshots / "model-provider-credential-saved.png"), full_page=True)

    clear_button.click()
    expect(page.get_by_text("OpenAI key cleared.", exact=True)).to_be_visible()
    expect(key_input).to_have_value("")
    expect(card.get_by_text("Saved key is readable.", exact=True)).to_have_count(0)
    expect(clear_button).to_be_disabled()
    assert len(patch_payloads) == 2

    page.reload()
    page.get_by_role("button", name="Model Providers").click()
    expect(key_input).to_have_value("")
    expect(clear_button).to_be_disabled()
    expect(page.locator("body")).not_to_contain_text(fixture_key)
    page.screenshot(path=str(screenshots / "model-provider-credential-cleared.png"), full_page=True)


###############################################################################
def test_geospatial_credential_safe_save_clear_and_reload(page: Page, base_url: str) -> None:
    patch_payloads: list[dict[str, Any]] = []
    _setup_stub_harness(page, patch_payloads=patch_payloads)
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{base_url.rstrip('/')}/settings")
    page.get_by_role("button", name="Geospatial Access").click()

    card = page.locator(".settings-provider-card").filter(
        has=page.get_by_role("heading", name="TomTom", exact=True)
    )
    key_input = card.get_by_label("TomTom API key")
    expect(card.get_by_text("Not configured")).to_be_visible()
    expect(key_input).to_have_attribute("type", "password")
    expect(key_input).to_have_value("")

    card.get_by_role("button", name="Save key").click()
    expect(
        page.get_by_text(
            "Enter a TomTom API key before saving, or clear the saved key.", exact=True
        )
    ).to_be_visible()
    assert patch_payloads == []

    fixture_key = "synthetic-tomtom-fixture"
    key_input.fill(fixture_key)
    card.get_by_role("button", name="Save key").click()
    expect(
        page.get_by_text(
            "TomTom key saved. Provider access has not been validated.", exact=True
        )
    ).to_be_visible()
    expect(key_input).to_have_value("")
    expect(card.get_by_text("Saved key is readable (not validated)")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text(fixture_key)
    assert len(patch_payloads) == 1

    screenshots = T1_10_SETTINGS_QA_DIR / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshots / "geospatial-credential-saved.png"), full_page=True)

    card.get_by_role("button", name="Save key").click()
    expect(
        page.get_by_text(
            "Enter a TomTom API key before saving, or clear the saved key.", exact=True
        )
    ).to_be_visible()
    assert len(patch_payloads) == 1

    card.get_by_role("button", name="Clear saved key").click()
    expect(
        page.get_by_text(
            "TomTom key cleared. Optional capabilities are disabled.", exact=True
        )
    ).to_be_visible()
    expect(card.get_by_text("Not configured")).to_be_visible()
    assert len(patch_payloads) == 2

    page.reload()
    expect(card.get_by_text("Not configured")).to_be_visible()
    page.screenshot(path=str(screenshots / "geospatial-credential-cleared.png"), full_page=True)


###############################################################################
def test_geospatial_credential_failed_updates_preserve_saved_state(
    page: Page, base_url: str
) -> None:
    settings_payload = selected_agent_settings_payload()
    settings_payload["credentials"] = {"tomtom": {"api_key": True}}
    settings_payload["credential_health"] = {"tomtom": {"api_key": "stored"}}
    patch_payloads: list[dict[str, Any]] = []
    _setup_stub_harness(
        page,
        settings_payload=settings_payload,
        patch_payloads=patch_payloads,
        settings_patch_failure=True,
    )
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{base_url.rstrip('/')}/settings")
    page.get_by_role("button", name="Geospatial Access").click()

    card = page.locator(".settings-provider-card").filter(
        has=page.get_by_role("heading", name="TomTom", exact=True)
    )
    key_input = card.get_by_label("TomTom API key")
    expect(card.get_by_text("Saved key is readable (not validated)")).to_be_visible()

    fixture_key = "synthetic-tomtom-replacement"
    key_input.fill(fixture_key)
    card.get_by_role("button", name="Save key").click()
    expect(page.get_by_text("Synthetic credential update failure.", exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            "TomTom key saved. Provider access has not been validated.", exact=True
        )
    ).to_have_count(0)
    expect(key_input).to_have_value(fixture_key)
    expect(key_input).to_have_attribute("type", "password")
    expect(page.locator("body")).not_to_contain_text(fixture_key)
    expect(card.get_by_text("Saved key is readable (not validated)")).to_be_visible()

    card.get_by_role("button", name="Clear saved key").click()
    expect(page.get_by_text("Synthetic credential update failure.", exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            "TomTom key cleared. Optional capabilities are disabled.", exact=True
        )
    ).to_have_count(0)
    expect(card.get_by_text("Saved key is readable (not validated)")).to_be_visible()
    assert len(patch_payloads) == 2

    screenshots = T1_10_SETTINGS_QA_DIR / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshots / "geospatial-credential-update-failure.png"), full_page=True)

###############################################################################
def test_capabilities_tables_do_not_clip_desktop_columns(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{base_url.rstrip('/')}/geodata")

    expect(page.get_by_role("heading", name="Map Types")).to_be_visible(timeout=15000)

    metrics = page.evaluate(
        """
        () => {
          const page = document.querySelector('.capabilities-page');
          const tableWraps = Array.from(document.querySelectorAll('.capability-table-wrap'));
          const pageRect = page.getBoundingClientRect();
          return {
            bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            wrappedTables: tableWraps.map((wrap) => {
              const rect = wrap.getBoundingClientRect();
              return { left: rect.left, right: rect.right, pageRight: pageRect.right };
            }),
          };
        }
        """
    )

    assert metrics["bodyOverflow"] <= 1
    assert metrics["wrappedTables"]
    assert all(
        item["right"] <= item["pageRight"] + 1 for item in metrics["wrappedTables"]
    )

###############################################################################
def test_chat_composer_does_not_cover_latest_assistant_message(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(
        page,
        turn_payload_factory=lambda _message: chat_completion_text_payload(
            12001,
            "This is the latest assistant response and it must remain visible above the composer.",
        ),
    )
    page.set_viewport_size({"width": 1024, "height": 844})
    page.goto(base_url)

    page.get_by_label("Chat message").fill("show status")
    page.get_by_role("button", name="Send message").click()
    latest = page.get_by_text(
        "This is the latest assistant response and it must remain visible above the composer."
    )
    expect(latest).to_be_visible(timeout=15000)

    metrics = page.evaluate(
        """
        () => {
          const assistant = Array.from(document.querySelectorAll('.chat-message--assistant')).at(-1);
          const composer = document.querySelector('.chat-composer');
          const a = assistant.getBoundingClientRect();
          const c = composer.getBoundingClientRect();
          return { assistantBottom: a.bottom, composerTop: c.top };
        }
        """
    )

    assert metrics["assistantBottom"] <= metrics["composerTop"] + 1

###############################################################################
def test_settings_query_params_do_not_leak_back_to_chat(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)

    page.goto(f"{base_url.rstrip('/')}/settings?mode=cloud")
    expect(page).to_have_url(re.compile(r".*/settings$"))

    page.get_by_role("link", name="Search").click()
    expect(page.get_by_label("Chat message")).to_be_visible(timeout=15000)

    path = page.evaluate("() => window.location.pathname")
    query = page.evaluate("() => window.location.search")
    assert path == "/"
    assert query == ""

###############################################################################
def test_settings_sections_preserve_drafts_save_and_return(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)
    page.set_viewport_size({"width": 1366, "height": 768})

    runtime_settings = {
        "schema_version": 1,
        **AppSettings.model_construct().runtime_payload(),
        "restart_required": False,
        "message": None,
    }
    captured_runtime_patches: list[dict[str, Any]] = []

    def handle_runtime_settings(route: Route) -> None:
        method = route.request.method.upper()
        if method == "GET":
            _json_ok(route, runtime_settings)
            return
        if method == "PATCH":
            patch = _request_json(route)
            captured_runtime_patches.append(patch)
            for block_name, block_patch in patch.items():
                if isinstance(block_patch, dict):
                    runtime_settings[block_name].update(block_patch)
            runtime_settings["restart_required"] = bool(patch)
            runtime_settings["message"] = (
                "Settings saved. Restart AEGIS to apply runtime changes."
                if patch
                else None
            )
            _json_ok(route, runtime_settings)
            return
        route.fulfill(
            status=405,
            content_type="application/json",
            body=json.dumps({"detail": "Method not allowed"}),
        )

    page.route(re.compile(r".*/settings/runtime(?:\?.*)?$"), handle_runtime_settings)
    page.goto(f"{base_url.rstrip('/')}/settings?tab=not-a-section")

    expect(page).to_have_url(f"{base_url.rstrip('/')}/settings")
    expect(page.get_by_role("button", name="Models", exact=True)).to_have_attribute(
        "aria-current", "page"
    )

    page.goto(f"{base_url.rstrip('/')}/settings?tab=map-search")
    expect(page.get_by_role("heading", name="Map & Search", exact=True)).to_be_visible(
        timeout=15000
    )

    sections = (
        ("Models", "/settings", None),
        ("Model Providers", "/settings?tab=model-providers", "Model providers"),
        (
            "Geospatial Access",
            "/settings?tab=geospatial-access",
            "Optional provider credentials",
        ),
        ("Application", "/settings?tab=application", "Application"),
        ("Map & Search", "/settings?tab=map-search", "Map & Search"),
        ("Data Sources", "/settings?tab=data-sources", "Data Sources"),
        ("Agent Runtime", "/settings?tab=agent-runtime", "Agent Runtime"),
    )
    t1_09_qa_dir = (
        Path(__file__).resolve().parents[3]
        / "assets"
        / "QA"
        / "tier1-validation-develop-20260923"
        / "T1-09"
    )
    screenshot_dir = t1_09_qa_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    for label, expected_url, heading in sections:
        page.get_by_role("button", name=label, exact=True).click()
        expect(page).to_have_url(f"{base_url.rstrip('/')}{expected_url}")
        if heading is None:
            expect(page.get_by_placeholder("Search models")).to_be_visible()
        else:
            expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible(
                timeout=15000
            )
        slug = label.lower().replace(" & ", "-").replace(" ", "-")
        page.screenshot(
            path=str(screenshot_dir / f"section-{slug}.png"), full_page=True
        )

    page.go_back()
    expect(page).to_have_url(f"{base_url.rstrip('/')}/settings?tab=data-sources")
    expect(page.get_by_role("heading", name="Data Sources", exact=True)).to_be_visible()
    page.go_forward()
    expect(page).to_have_url(f"{base_url.rstrip('/')}/settings?tab=agent-runtime")
    expect(page.get_by_role("heading", name="Agent Runtime", exact=True)).to_be_visible()

    page.get_by_role("button", name="Application", exact=True).click()
    history_limit = page.get_by_label("Maximum history messages")
    history_limit.fill("23")
    page.get_by_role("button", name="Data Sources", exact=True).click()
    page.get_by_role("button", name="Application", exact=True).click()
    history_limit = page.get_by_label("Maximum history messages")
    expect(history_limit).to_have_value("23")
    page.screenshot(
        path=str(screenshot_dir / "application-draft-retained.png"), full_page=True
    )

    with page.expect_response(
        lambda response: response.request.method == "PATCH"
        and response.url.endswith("/settings/runtime")
    ) as patch_response:
        page.get_by_role("button", name="Save application settings").click()
    assert patch_response.value.ok, patch_response.value.status
    assert captured_runtime_patches[-1]["chat"]["max_history_messages"] == 23

    page.get_by_role("link", name="Search", exact=True).click()
    expect(page.get_by_label("Chat message")).to_be_visible(timeout=15000)
    page.get_by_role("link", name="Settings", exact=True).click()
    page.get_by_role("button", name="Application", exact=True).click()
    history_limit = page.get_by_label("Maximum history messages")
    expect(history_limit).to_have_value("23")
    page.screenshot(
        path=str(screenshot_dir / "application-saved-after-return.png"), full_page=True
    )

###############################################################################
def test_coordinate_lookup_and_place_search_follow_distinct_ui_paths(
    page: Page, base_url: str
) -> None:
    def turn_payload(message: str) -> dict[str, Any]:
        message = message.lower()
        if "coordinate" in message:
            return chat_completion_text_payload(
                11001, "Coordinates identified without map session."
            )
        return chat_completion_map_payload(
            11001, "Place search rendered with an interactive map."
        )

    _setup_stub_harness(page, turn_payload_factory=turn_payload)

    page.goto(base_url)
    composer = page.get_by_label("Chat message")

    composer.fill("coordinate lookup for Eiffel Tower")
    page.get_by_role("button", name="Send message").click()
    expect(
        page.get_by_text("Coordinates identified without map session.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_have_count(0)
    expect(page.locator(".overlay-controls")).to_have_count(0)

    page.get_by_role("button", name="Start new chat").click()
    expect(page.get_by_label("Chat message")).to_be_visible(timeout=15000)
    composer.fill("place search for Rome city center")
    page.get_by_role("button", name="Send message").click()
    expect(
        page.get_by_text("Place search rendered with an interactive map.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=15000)
