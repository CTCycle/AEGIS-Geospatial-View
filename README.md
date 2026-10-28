<p align="center"><img src="assets/figures/aegis-mark.svg" alt="AEGIS mark" width="72"></p>

<h1 align="center">AEGIS Geospatial View</h1>

<p align="center">Explore places and geospatial data through chat and a map.</p>

<p align="center">
  <a href="#search">Search</a> ·
  <a href="#geodata">Geodata</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="assets/docs/project_index.md">Documentation</a>
</p>

<p align="center"><img src="assets/figures/workspace.png" alt="AEGIS Search workspace with chat beside the map canvas" width="100%"></p>

AEGIS is a local geospatial workspace. Ask about a place or an area in chat, then inspect the returned map session and its overlays alongside the conversation.

The map canvas starts empty and fills when a request returns a map session.

## Search

Ask for a location, coordinates, or a regional comparison. Follow-up messages can refine the request, zoom the map, or add, hide, and remove overlays in the current conversation.

Try:

- `Show current satellite context for Rome, Italy.`
- `Where in Europe did it rain most today?`
- `Give me the coordinates of Rome, Italy.`

Regional comparisons use ranked samples or grid bins and report source and coverage context. Weather grid values are model estimates, not station measurements. With a vision-capable model, you can also attach a photo and ask for location clues; treat the suggested place as a hypothesis.

## Geodata

The catalog lists providers, basemaps, overlays, camera networks, transit feeds, and direct tools. Each entry includes source, coverage or scope, update information, access notes, and dependencies.

<p align="center"><img src="assets/figures/geodata-catalog.png" alt="AEGIS Geodata catalog showing providers, data sources, and access requirements" width="100%"></p>

Coverage, availability, credentials, quotas, attribution, and reuse terms vary by source. Check the catalog and provider terms before relying on a dataset.

## Quick start

AEGIS currently runs on Windows. Use PowerShell 7 or later and a desktop browser viewport at least 1024 pixels wide. From the repository root, run:

```powershell
.\start_on_windows.ps1
```

Choose **Launch application**. On first use, the launcher prepares portable Python, `uv`, and Node.js runtimes, synchronizes dependencies, and builds the frontend when needed. It opens the app after the backend is ready. Keep the launcher open while using AEGIS; press **Ctrl+C** to stop it.

Before sending a chat request, select an agent model in **Settings → Models**. The model must support native tool calling and structured output. Install an Ollama model for local use, or configure credentials under **Settings → Model Providers** for a hosted model.

## Configuration

Some geospatial sources need credentials; others are available without a key. Manage source credentials in **Settings → Geospatial Access**. Keys entered in Settings are encrypted in the active SQLite database.

The default data root is `data/runtime`. Set `AEGIS_DATA_DIR` in `settings/.env` to use another location. See the [runtime configuration guide](assets/docs/runtime/configuration.md) for the available settings.

## Development

| Area | Technology |
| --- | --- |
| Web client | Angular and TypeScript |
| API | FastAPI and Python 3.14+ |
| Map | MapLibre GL JS |
| Storage | SQLite and Alembic |
| Windows launcher | PowerShell 7+ |

For manual startup and test commands, see [Runtime startup](assets/docs/runtime/startup.md). The [documentation index](assets/docs/project_index.md) links to architecture, user workflows, and operating guides.

## License

AEGIS Geospatial View is licensed under the [MIT License](LICENSE).

<p align="center"><sub>Last updated: 2026-10-28</sub></p>
