"""
E2E tests for AEGIS UI navigation and key user flows.
Exercises sidebar navigation, form validation, and map rendering.
"""
from playwright.sync_api import Page, expect


class TestAppShell:
    """Smoke tests for the main UI layout."""

    def test_homepage_loads_with_core_panels(self, page: Page, base_url: str):
        page.goto(base_url)
        expect(page.get_by_text("AEGIS", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="AEGIS Geographics")).to_be_visible()
        expect(page.get_by_text("Location search")).to_be_visible()
        expect(page.get_by_text("Map statistics")).to_be_visible()


class TestNavigation:
    """Navigation tests for sidebar page switching."""

    def test_navigate_to_database_browser(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Database Browser").click()
        expect(page.get_by_role("heading", name="Database Browser")).to_be_visible()
        expect(page.get_by_label("Select Table")).to_be_visible()

    def test_return_to_maps_page(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Database Browser").click()
        page.get_by_role("button", name="Geospatial View").click()
        expect(page.get_by_role("heading", name="AEGIS Geographics")).to_be_visible()


class TestDatabaseBrowserUI:
    """UI tests for database table browsing."""

    def test_refresh_loads_table_stats(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Database Browser").click()
        expect(page.locator("#table-select")).to_be_enabled()
        page.get_by_title("Refresh data").click()
        expect(page.locator(".stats-row")).to_be_visible(timeout=15000)


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
