"""
E2E tests for AEGIS UI navigation and key user flows.
Exercises top-tab shell, form validation, and map rendering.
"""

from playwright.sync_api import Page, expect


class TestAppShell:
    """Smoke tests for the main UI layout."""

    def test_homepage_loads_with_core_panels(self, page: Page, base_url: str):
        page.goto(base_url)
        expect(page.get_by_text("AEGIS", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="AEGIS Geospatial View")).to_be_visible()
        expect(page.get_by_text("Search Commands")).to_be_visible()
        expect(page.get_by_role("tab", name="Geospatial View")).to_be_visible()
        expect(page.get_by_text("Map statistics")).to_be_visible()


class TestSearchUI:
    """UI tests for location search inputs and rendering."""

    def test_empty_address_shows_validation(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Search").click()
        expect(page.get_by_text("Enter an address")).to_be_visible()

    def test_coordinate_search_renders_map(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Coordinates").click()
        page.get_by_label("Latitude").fill("41.9028")
        page.get_by_label("Longitude").fill("12.4964")
        page.get_by_role("button", name="Search").click()
        expect(page.locator("iframe.map-iframe")).to_be_visible(timeout=45000)
