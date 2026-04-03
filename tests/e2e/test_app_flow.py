"""
E2E tests for AEGIS chat-first UI flow.
"""

from playwright.sync_api import Page, expect


class TestAppShell:
    def test_homepage_loads_chat_and_map_layout(self, page: Page, base_url: str):
        page.goto(base_url)
        expect(page.get_by_text("AEGIS", exact=True)).to_be_visible()
        expect(page.get_by_text("Operations Console")).to_be_visible()
        expect(page.get_by_text("Agent Chat")).to_be_visible()
        expect(page.locator(".map-canvas")).to_be_visible()


class TestChatFlow:
    def test_chat_composer_visible_and_send_prompt(self, page: Page, base_url: str):
        page.goto(base_url)
        composer = page.get_by_label("Chat message")
        expect(composer).to_be_visible()
        composer.fill("show map at 41.9028, 12.4964")
        page.get_by_role("button", name="Send").click()
        expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
        expect(page.get_by_text("Search executed successfully.")).to_be_visible(timeout=45000)

    def test_settings_page_opens_from_toolbar(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Open settings").click()
        expect(page.get_by_text("Model Settings")).to_be_visible()
        expect(page.get_by_text("Vectorize all available manifests")).to_be_visible()

    def test_model_selection_persists(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Open settings").click()
        page.get_by_role("button", name="Cloud").click()
        first_card_button = page.locator(".model-card__actions button", has_text="Use for chat").first
        first_card_button.click()
        expect(page.get_by_text("Selected")).to_be_visible(timeout=15000)
