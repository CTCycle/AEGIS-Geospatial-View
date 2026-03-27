# HOW TO TEST

This document describes the testing strategy and instructions for the project.
Tests must cover end-to-end scenarios that exercise both the UI and backend.
Coverage includes REST APIs, UI widgets, input validation, database interactions,
and geospatial search flows.

## Overview
We use **End-to-End (E2E)** testing to validate the entire application stack
(Frontend + Backend + Database).
- **Framework**: [Playwright](https://playwright.dev/python/) with
  [pytest](https://docs.pytest.org/).
- **Language**: Python.

## Test Suite Structure
```
tests/
|-- run_tests.bat             # Automated test runner (Windows)
|-- conftest.py               # Pytest configuration and fixtures
`-- e2e/
    |-- test_app_flow.py       # UI navigation + search flows
    `-- test_maps_api.py       # /maps/search validation + overlays
```

## Quick Start (Recommended)

### Fully Automated Testing
Run the batch file. It handles setup, server startup, and cleanup:
```cmd
tests\run_tests.bat
```

This script will:
1. Check that prerequisites are installed
2. Install Playwright browsers if needed
3. Start the backend server
4. Start the frontend server
5. Run all tests
6. Stop the servers and report results

> [!TIP]
> Run `AEGIS\start_on_windows.bat` at least once before running tests to ensure
> all dependencies are installed.

---

## Manual Testing

### Prerequisites
- Python 3.14+ with `pytest` and `pytest-playwright`
- Playwright browsers installed

### Setup
1. **Install Test Dependencies**:
   ```cmd
   pip install .[test]
   ```

2. **Install Playwright Browsers**:
   ```cmd
   python -m playwright install
   ```

### Running Tests Manually
1. **Start the Application**:
   ```cmd
   AEGIS\start_on_windows.bat
   ```

2. **Run Tests** (in a separate terminal):
   ```cmd
   pytest tests
   ```

### Useful Options
| Option | Description |
|--------|-------------|
| `--headed` | Run with browser visible |
| `--slowmo 1000` | Slow down execution (ms) |
| `--video on` | Record video of tests |
| `-v` | Verbose output |
| `-x` | Stop on first failure |
| `-k "test_name"` | Run specific test by name |

**Example**: Run UI tests with visible browser:
```cmd
pytest tests/e2e/test_app_flow.py --headed --slowmo 500
```

---

## Writing New Tests

- **Location**: Place tests in `tests/e2e/`
- **Naming**: Files must start with `test_`
- **Fixtures**:
  - `page`: Playwright browser automation
  - `api_context`: API request context
  - `base_url`: UI base URL
  - `api_base_url`: API base URL

### Example API Test
```python
def test_map_search(api_context):
    payload = {
        "datetime": "2024-06-15T12:00:00",
        "use_coordinates": True,
        "latitude": 41.9028,
        "longitude": 12.4964,
    }
    response = api_context.post("/maps/search", data=payload)
    assert response.ok
```
Note: Playwright Python serializes dicts passed via `data=` as JSON; `json=`
is not a valid argument for `APIRequestContext.post`.

### Example UI Test
```python
from playwright.sync_api import expect

def test_navigation(page, base_url):
    page.goto(base_url)
    expect(page.get_by_role("tab", name="Geospatial View")).to_be_visible()
    expect(page.get_by_role("heading", name="AEGIS Geospatial View")).to_be_visible()
```
If a text locator matches multiple nodes, prefer `get_by_role` or
`get_by_text(..., exact=True)` to avoid strict-mode collisions.

### External Dependencies
`/maps/search` uses external geospatial services (Nominatim, OpenAQ,
Open-Elevation, and optionally NASA GIBS overlays). Ensure network access is
available when running E2E tests.

## Troubleshooting
- **Connection Refused**: Ensure the app is running before tests.
- **Playwright not found**: Use `python -m playwright install`.
- **Timeouts on map search**: Verify external network access for geospatial APIs.
