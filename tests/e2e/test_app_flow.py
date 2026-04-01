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
        expect(page.get_by_text("Operations Console")).to_be_visible()
        expect(page.get_by_text("Search Commands")).to_be_visible()
        expect(page.get_by_text("Location search")).to_be_visible()
        expect(page.get_by_text("Map context")).to_be_visible()


class TestSearchUI:
    """UI tests for location search inputs and rendering."""

    def test_empty_address_shows_validation(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Search", exact=True).click()
        expect(page.get_by_text("Enter an address")).to_be_visible()

    def test_coordinate_search_renders_map(self, page: Page, base_url: str):
        page.goto(base_url)
        page.get_by_role("button", name="Coordinates", exact=True).click()
        page.get_by_label("Latitude").fill("41.9028")
        page.get_by_label("Longitude").fill("12.4964")
        page.get_by_role("button", name="Search", exact=True).click()
        expect(page.locator(".maplibre-container")).to_be_visible(timeout=45000)

    def test_eea_esa_overlay_requests_use_expected_protocols(
        self, page: Page, base_url: str
    ):
        captured_urls: list[str] = []

        def track_request(request) -> None:
            url = request.url
            if (
                "noise.discomap.eea.europa.eu" in url
                or "services.terrascope.be" in url
            ):
                captured_urls.append(url)

        page.on("request", track_request)
        page.goto(base_url)
        page.get_by_role("button", name="Coordinates", exact=True).click()
        page.get_by_label("Latitude").fill("41.9028")
        page.get_by_label("Longitude").fill("12.4964")
        page.get_by_role("button", name="EEA Noise Exposure 2019", exact=True).click()
        page.get_by_role("button", name="ESA WorldCover", exact=True).click()
        page.get_by_role("button", name="Search", exact=True).click()
        expect(page.locator(".maplibre-container")).to_be_visible(timeout=45000)
        page.wait_for_timeout(6000)

        esa_urls = [u for u in captured_urls if "services.terrascope.be" in u]
        eea_urls = [u for u in captured_urls if "noise.discomap.eea.europa.eu" in u]
        assert esa_urls, "Expected at least one ESA WorldCover tile request."
        assert eea_urls, "Expected at least one EEA noise tile request."
        assert any("request=GetTile" in u for u in esa_urls)
        assert all("request=GetMap" not in u for u in esa_urls)
        assert any("exceptions=application%2Fvnd.ogc.se_inimage" in u for u in eea_urls)
