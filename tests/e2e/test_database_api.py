"""
E2E tests for Database Browser API endpoints.
Tests: /browser/tables, /browser/tables/{name}, /browser/tables/{name}/stats
"""

from playwright.sync_api import APIRequestContext


class TestBrowserEndpoints:
    """Tests for the /browser/* API endpoints."""

    def test_list_tables_returns_expected_tables(self, api_context: APIRequestContext):
        """GET /browser/tables should return the list of available tables."""
        response = api_context.get("/browser/tables")
        assert response.ok, f"Expected 200, got {response.status}"

        data = response.json()
        assert isinstance(data, dict), "Response should be an object"
        assert "tables" in data
        assert isinstance(data["tables"], list)

        table_names = {entry.get("name") for entry in data["tables"]}
        assert "GIBS_LAYERS" in table_names
        assert "SEARCH_SESSIONS" in table_names

    def test_get_table_data_valid_table(self, api_context: APIRequestContext):
        """GET /browser/tables/{table_name} should return table data."""
        response = api_context.get("/browser/tables/GIBS_LAYERS")
        assert response.ok, f"Expected 200, got {response.status}"

        data = response.json()
        assert data["tableName"] == "GIBS_LAYERS"
        assert isinstance(data.get("displayName"), str)
        assert isinstance(data.get("columns"), list)
        assert isinstance(data.get("rows"), list)
        assert isinstance(data.get("rowCount"), int)
        assert isinstance(data.get("columnCount"), int)
        assert data["columnCount"] == len(data["columns"])
        assert data["rowCount"] == len(data["rows"])

    def test_get_table_stats_valid_table(self, api_context: APIRequestContext):
        """GET /browser/tables/{table_name}/stats should return row/column counts."""
        response = api_context.get("/browser/tables/SEARCH_SESSIONS/stats")
        assert response.ok

        data = response.json()
        assert data["tableName"] == "SEARCH_SESSIONS"
        assert isinstance(data.get("displayName"), str)
        assert isinstance(data.get("rowCount"), int)
        assert isinstance(data.get("columnCount"), int)
        assert data["columnCount"] > 0

    def test_get_table_data_invalid_table_returns_404(
        self, api_context: APIRequestContext
    ):
        """GET /browser/tables/{invalid} should return 404."""
        response = api_context.get("/browser/tables/NOT_A_TABLE")
        assert response.status == 404

    def test_get_table_stats_invalid_table_returns_404(
        self, api_context: APIRequestContext
    ):
        """GET /browser/tables/{invalid}/stats should return 404."""
        response = api_context.get("/browser/tables/NOT_A_TABLE/stats")
        assert response.status == 404
