# AEGIS Geospatial View

<p align="center"><img src='app/client/public/favicon.png' alt='AEGIS mark' width="112"></p>

**A chat-driven local geospatial workspace for exploring places, layers, and map context.**


[![License](https://img.shields.io/github/license/CTCycle/AEGIS-Geospatial-View?style=flat-square)](LICENSE) [![Release](https://img.shields.io/github/v/release/CTCycle/AEGIS-Geospatial-View?display_name=tag&style=flat-square)](https://github.com/CTCycle/AEGIS-Geospatial-View/releases) [![CI](https://img.shields.io/github/actions/workflow/status/CTCycle/AEGIS-Geospatial-View/ci.yml?branch=develop&label=CI&style=flat-square)](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/workflows/ci.yml?query=branch%3Adevelop) [![Python](https://img.shields.io/badge/Python-3.14.7-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/) [![Angular](https://img.shields.io/badge/Angular-22-DD0031?logo=angular&logoColor=white&style=flat-square)](https://angular.dev/) [![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white&style=flat-square)](https://www.microsoft.com/windows)

## Overview

AEGIS turns location questions into map-focused results. Describe a place, coordinates, or a geospatial task in plain language, review the map and available overlays, and refine the result with follow-up requests. The local web application includes a Workspace, a Geodata catalog, and Settings.

The default workflow can use public geospatial sources without a provider key. Optional cloud models and provider services require their own access and availability.

## Key Features

- Search by address or coordinates and review the location in its map context.
- Explore base maps, overlays, and other geospatial capabilities in the Geodata catalog.
- Refine a map session with follow-up requests while preserving conversation context.
- Configure model selection, local Ollama access, provider credentials, and geospatial settings from the application.
- Keep local application state in SQLite, with schema changes managed through Alembic.

## Technology Stack

- Python 3.14.7 and FastAPI backend.
- Angular 22 web client with a local map interface.
- SQLite database by default.
- The Windows launcher prepares portable Python, uv, and Node.js runtimes.

## Installation and Usage

From the repository root in PowerShell, start the launcher:

```powershell
.\start_on_windows.ps1
```

Choose **Launch Application** and open the local address reported by the launcher. On first setup, the launcher prepares the runtimes and dependencies. Use a desktop browser window at least 1024 pixels wide; the interface does not provide a mobile layout.

## Configuration

Startup and deployment values are stored in `settings/.env`, created from `settings/.env.example` when missing. `AEGIS_DATA_DIR` can select a different local data directory. Enter optional model-provider credentials through **Settings**; the public-source workflow does not require them.

## Documentation

- [Quick Start](assets/docs/user/quick_start.md)
- [Runtime startup](assets/docs/runtime/startup.md)
- [Runtime configuration](assets/docs/runtime/configuration.md)
- [Troubleshooting](assets/docs/user/troubleshooting.md)

## License

Licensed under the MIT License. See [LICENSE](LICENSE).
