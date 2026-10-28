<p align="center"><img src="app/client/public/favicon.png" alt="" width="80"></p>

<h1 align="center">AEGIS Geospatial View</h1>

<p align="center">Ask geospatial questions in chat and inspect results on a map.</p>

<p align="center">
  <a href="#search">Search</a> ·
  <a href="#geodata">Geodata</a> ·
  <a href="#run-aegis">Run AEGIS</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="assets/docs/project_index.md">Documentation</a>
</p>

<p align="center"><img src="assets/figures/workspace.png" alt="AEGIS Search workspace with chat and map canvas ready for a request" width="760"></p>

AEGIS is a local geospatial workspace with two main areas: **Search**, for asking questions and exploring results on a map, and **Geodata**, for browsing available sources and their access requirements.

## Search

Describe a place, coordinates, or a geospatial question. The selected model can use AEGIS tools to return a written answer, a map session, or both. Follow-up requests can refine the question or change active overlays while keeping the conversation context.

Search supports:

- Place and coordinate lookup.
- Regional comparisons using ranked samples or grid bins. Results include source and coverage context; weather values are model estimates, not station measurements.
- Adding, hiding, and removing map overlays through follow-up messages.
- Photo-based location clues with a vision-capable model. These are hypotheses, and AEGIS asks for confirmation when clues are ambiguous.

Try prompts such as:

- `Show current satellite context for Rome, Italy.`
- `Where in Europe did it rain most today?`
- `Give me the coordinates of Rome, Italy.`

## Geodata

The catalog lists providers, basemaps, layers, camera networks, transit feeds, and direct tools available to the application. Entries include source and access notes.

<p align="center"><img src="assets/figures/geodata-catalog.png" alt="Geodata catalog showing providers, sources, and access notes" width="760"></p>

Coverage, freshness, credentials, and usage terms vary by provider. Check the catalog and provider terms before relying on a source.

## Run AEGIS

On Windows, use PowerShell 7 or later. From the repository root, run:

```powershell
.\start_on_windows.ps1
```

Choose **Launch application**. On first use, the launcher prepares its portable Python, `uv`, and Node.js runtimes, synchronizes dependencies, and builds the frontend when needed. It opens the app when the backend is ready. Press **Ctrl+C** in the launcher to stop it.

Chat requires a model with native tool-calling support. Select an installed Ollama model in **Settings → Models**, or configure a supported cloud provider in **Settings → Model Providers**. Some optional data sources also require credentials.

The application requires a desktop browser viewport at least 1024 pixels wide; smaller windows show a minimum-size notice instead of a mobile layout. For manual development setup, see [Runtime startup](assets/docs/runtime/startup.md).

## Configuration

Application data is stored in SQLite under `data/runtime` by default. Set `AEGIS_DATA_DIR` in `settings/.env` to choose another data directory. Provider keys entered in Settings are encrypted in the local database. The [runtime configuration guide](assets/docs/runtime/configuration.md) documents the available settings.

## Development

| Area | Stack |
| --- | --- |
| Web client | Angular 22, TypeScript 6 |
| API | Python 3.14+, FastAPI |
| Map | MapLibre GL JS |
| Storage | SQLite, Alembic migrations |
| Windows launcher | PowerShell 7+ |

The [project documentation index](assets/docs/project_index.md) links to the architecture, user guides, runtime notes, and coding standards. Start with [Quick start](assets/docs/user/quick_start.md), [User workflows](assets/docs/user/workflows.md), and [Troubleshooting](assets/docs/user/troubleshooting.md) for application guidance.

## License

AEGIS Geospatial View is licensed under the [MIT License](LICENSE).
