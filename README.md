<p align="center"><img src="app/client/public/favicon.png" alt="AEGIS mark" width="96"></p>

<h1 align="center">AEGIS Geospatial View</h1>

<p align="center">A chat-driven local geospatial workspace for exploring places, layers, and map context.</p>

<p align="center">
  <a href="https://github.com/CTCycle/AEGIS-Geospatial-View/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/CTCycle/AEGIS-Geospatial-View?style=flat-square"></a>
  <a href="https://github.com/CTCycle/AEGIS-Geospatial-View/commits"><img alt="Last commit" src="https://img.shields.io/github/last-commit/CTCycle/AEGIS-Geospatial-View?style=flat-square"></a>
  <a href="https://github.com/CTCycle/AEGIS-Geospatial-View/releases"><img alt="Release" src="https://img.shields.io/github/v/release/CTCycle/AEGIS-Geospatial-View?display_name=tag&style=flat-square"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/CTCycle/AEGIS-Geospatial-View?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.14.7" src="https://img.shields.io/badge/Python-3.14.7-3776AB?logo=python&logoColor=white&style=flat-square"></a>
  <a href="https://angular.dev/"><img alt="Angular 22" src="https://img.shields.io/badge/Angular-22-DD0031?logo=angular&logoColor=white&style=flat-square"></a>
  <a href="https://www.microsoft.com/windows"><img alt="Platform: Windows" src="https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white&style=flat-square"></a>
</p>

## Overview

AEGIS Geospatial View is a chat-driven local geospatial workspace for exploring places, layers, and map context. Users describe a location, coordinates, or geospatial task in plain language and receive map-focused results with overlays and session context. The application can refine results through follow-up requests while preserving conversation context and supports direct coordinate lookups. It can discover conditions across an area and locate photos from visual clues using a vision-capable model. The default workflow uses public geospatial sources without a provider key, while optional cloud models and provider services require their own access. Local state persists in SQLite, and the interface requires a desktop browser window at least 1024 pixels wide.

## Key Features

- Search by address or coordinates and review locations in their map context.
- Explore base maps, overlays, and geospatial capabilities in the Geodata catalog.
- Refine a map session with follow-up requests while preserving conversation context.
- Discover conditions across an area with ranked samples, grid bins, and named places.
- Locate a photo from visual cues as a hypothesis with confirmation.
- Configure model selection, local Ollama access, provider credentials, and geospatial settings.
- Keep local application state in SQLite with schema migrations via Alembic.
- Use public sources by default, with optional provider keys for services such as TomTom and OpenAQ.

## Screenshots

<p align="center">
  <kbd><img src="assets/figures/search_page.png" alt="Search page" width="49%"></kbd>
  <kbd><img src="assets/figures/database_browser.png" alt="Database browser" width="49%"></kbd>
</p>
<p align="center"><em>Search page and database browser.</em></p>

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14.7, FastAPI 0.136.3 |
| Web client | Angular 22 (TypeScript 6.0) |
| Database | SQLite (default) |
| Schema migrations | Alembic |
| Launcher | Windows PowerShell with portable Python, uv, and Node.js |

## Installation and Usage

From the repository root in PowerShell, start the launcher:

```powershell
.\start_on_windows.ps1
```

Choose **Launch Application** and open the local address reported by the launcher. On first setup, the launcher prepares the runtimes and dependencies. Use a desktop browser window at least 1024 pixels wide; the interface does not provide a mobile layout.

Manual (from source):

```powershell
cd app/server
uv sync
cd ../client
npm install
```

Then launch the application (the backend serves the built UI and API at `http://<FASTAPI_HOST>:<FASTAPI_PORT>/`; press Ctrl+C in the launcher to stop) following [Runtime startup](assets/docs/runtime/startup.md).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `FASTAPI_HOST` | `127.0.0.1` | Backend host |
| `FASTAPI_PORT` | `5002` | Backend port |
| `UI_HOST` | `127.0.0.1` | Angular dev-server host (development only) |
| `UI_PORT` | `5000` | Angular dev-server port (development only) |
| `RELOAD` | `false` | Enable backend reload |
| `BACKEND_LOGS_VISIBLE` | `true` | Show backend logs |
| `REALTIME_ALLOW_MISSING_ORIGIN` | `false` | Allow missing-origin WebSocket connections |
| `AEGIS_ALLOW_RESTRICTED_SOURCES` | `false` | Enable restricted public sources |
| `AEGIS_DATA_DIR` | empty | Application data directory override |

Startup and deployment values are stored in `settings/.env`, created from `settings/.env.example` when missing. `AEGIS_DATA_DIR` can select a different local data directory. Enter optional model-provider credentials through **Settings**; the public-source workflow does not require them.

## Documentation

- [Quick Start](assets/docs/user/quick_start.md)
- [Runtime startup](assets/docs/runtime/startup.md)
- [Runtime configuration](assets/docs/runtime/configuration.md)
- [Troubleshooting](assets/docs/user/troubleshooting.md)

## Limitations

- The interface requires a desktop browser window at least 1024 pixels wide; no mobile layout is provided.
- Optional cloud models and provider services require their own access and availability.
- Restricted public sources remain unavailable unless explicitly enabled by the deployment owner.

## Contributing

Contributions are welcome. Open an issue or pull request with a clear description of the change and its motivation.

## License

Licensed under the MIT License. See [LICENSE](LICENSE).
