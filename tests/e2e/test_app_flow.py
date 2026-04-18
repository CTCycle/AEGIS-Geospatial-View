"""
E2E tests for AEGIS chat-first UI flow.
"""

from playwright.sync_api import Page, expect


class TestAppShell:
    def test_homepage_loads_chat_and_map_layout(self, page: Page, base_url: str):
        page.goto(base_url)
        expect(page.get_by_text("AEGIS", exact=True)).to_be_visible()
        expect(
            page.get_by_text("Enter a location-based request to begin.")
        ).to_be_visible()
        expect(page.get_by_label("Agent Chat")).to_be_visible()
        expect(page.locator(".map-canvas")).to_be_visible()


class TestChatFlow:
    def test_chat_composer_visible_and_send_prompt(self, page: Page, base_url: str):
        page.goto(base_url)
        composer = page.get_by_label("Chat message")
        expect(composer).to_be_visible()
        composer.fill("show map at 41.9028, 12.4964")
        page.get_by_role("button", name="Send").click()
        expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
        expect(page.locator(".chat-message--assistant").last).to_be_visible(
            timeout=45000
        )

    def test_settings_page_opens_from_toolbar(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Open settings").click()
        expect(page).to_have_url(f"{base_url.rstrip('/')}/settings")
        expect(page.get_by_text("Model Settings")).to_be_visible()
        expect(page.get_by_placeholder("Search models")).to_be_visible()
        expect(page.get_by_role("button", name="All")).to_be_visible()
        expect(page.get_by_role("button", name="Open Ollama settings")).to_be_visible()

    def test_back_forward_restores_route_and_settings_search(
        self, page: Page, base_url: str
    ):
        page.goto(base_url)
        page.get_by_role("button", name="Open settings").click()
        search = page.get_by_placeholder("Search models")
        search.fill("gpt")
        page.go_back()
        expect(page.get_by_label("Chat message")).to_be_visible()
        page.go_forward()
        expect(page.get_by_text("Model Settings")).to_be_visible()
        expect(search).to_have_value("gpt")

    def test_refresh_restores_chat_draft(self, page: Page, base_url: str):
        page.goto(base_url)
        composer = page.get_by_label("Chat message")
        composer.fill("draft message should persist")
        page.reload()
        expect(page.get_by_label("Chat message")).to_have_value(
            "draft message should persist"
        )

    def test_settings_query_deeplink_restores_search_and_mode(
        self, page: Page, base_url: str
    ):
        page.goto(f"{base_url.rstrip('/')}/settings?q=gpt&mode=cloud")
        expect(page.get_by_placeholder("Search models")).to_have_value("gpt")
        expect(page).to_have_url(f"{base_url.rstrip('/')}/settings?q=gpt&mode=cloud")

    def test_model_selection_persists(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Open settings").click()
        first_card_button = page.locator(
            ".model-card__actions button", has_text="Use for chat"
        ).first
        if first_card_button.count() == 0:
            expect(page.locator(".settings-empty-state").first).to_be_visible()
            return
        first_card_button.click()
        expect(page.get_by_text("Selected")).to_be_visible(timeout=15000)
