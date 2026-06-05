# AEGIS Geospatial View
[![Release](https://img.shields.io/github/v/release/CTCycle/AEGIS-geographics?display_name=tag)](https://github.com/CTCycle/AEGIS-geographics/releases)
[![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)](./app/server/pyproject.toml)
[![Angular](https://img.shields.io/badge/Angular-19.2-red?logo=angular&logoColor=white)](./app/client/package.json)
[![License](https://img.shields.io/github/license/CTCycle/AEGIS-geographics)](./LICENSE)
[![CI](https://github.com/CTCycle/AEGIS-geographics/actions/workflows/ci.yml/badge.svg)](https://github.com/CTCycle/AEGIS-geographics/actions/workflows/ci.yml)


AEGIS Geospatial View is a place-focused workspace built around conversation.

Instead of starting with menus and forms, you start with a question. You can ask for a city, a region, coordinates, or a specific map-based task, and the app helps turn that request into a useful geospatial view. The result is designed to feel like a guided workbench for exploring locations, layers, and map context without needing to know every tool in advance.

The app is most useful when you want to:

- look up a place and see it in context
- ask for coordinates directly
- zoom in or narrow a previous result
- explore available geospatial layers
- manage access for external map-related services
- adjust which models or assistants the app should use

## What You Can Do

The app is intentionally broad, but the everyday workflow is simple.

- Ask for a location in plain language.
- Add extra detail such as imagery, overlays, or a specific focus.
- Review the response and the map area that comes with it.
- Refine the result with follow-up messages instead of starting over.
- Switch to the geodata, access, or settings pages when you need more control.

Common examples include:

- “Show current satellite context for Rome, Italy.”
- “Give me the coordinates of Rome, Italy.”
- “Focus the previous result on environmental layers.”
- “Show available layers.”
- “Zoom in.”

## How To Move Around The App

The app is organized around a few main places. Each one has a clear purpose.

- `Workspace` is the main place to ask questions and review results.
- `Geodata` is where you can browse the available map and data capabilities.
- `Access configurations` is where optional provider access is managed.
- `Model settings` is where you choose how the assistant should behave.

The top navigation bar is the quickest way to move between these areas. If you are unsure where something lives, start in the workspace and use the top-level navigation from there.

## The Main Workspace

The workspace is the center of the app and is meant to feel like a conversation with a map attached.

It is split into two parts:

- a left-side area for chat, controls, and status
- a map area for viewing the geospatial result

The divider between these areas can be resized, so you can give more room to the conversation or more room to the map depending on what you are doing. The left side can also be collapsed when you want to focus on the map.

What you will usually do here:

1. Enter a request in the chat box.
2. Send it and wait for the reply.
3. Review the map and any overlays or supporting details.
4. Refine the result with another message if needed.

## How To Use The Chat

The chat is the main way to operate the app.

Use it when you want to ask about a place, explore a region, or narrow a result. You do not need to write formal commands. Short, direct requests are usually enough.

A good prompt normally includes:

- the location
- the thing you want to know or see
- any useful detail that helps narrow the result

Examples:

- `Paris, France`
- `Show me the area around the Colosseum.`
- `Find the coordinates for Florence, Italy.`
- `Refine the previous result to focus on nearby environmental layers.`

Helpful interaction habits:

- Use follow-up messages to refine the same topic.
- Ask for zoom changes if the area is too broad.
- Ask for a plain coordinate answer when you do not need the map itself.
- Use `Shift+Enter` when you want a new line in a longer message.
- Use `Enter` to send the message.

## What The App Can Show

Depending on the request and the available data, the app can provide different kinds of geospatial help.

- a map-centered view of the area you asked for
- overlay information when it is available
- session-aware follow-up results so later questions stay connected
- a list of available geodata capabilities
- lightweight zooming and map-focused refinements

The exact result depends on what kind of request you make and what sources are available at the time.

## Geodata, Access, And Settings

These pages are there for when you want more control than the workspace alone provides.

### Geodata

Use this page to understand what kinds of geospatial capabilities are available. It is useful when you want to know what the app can work with before you ask for it in chat.

### Access Configurations

Use this page if you need optional provider access for certain geospatial services. The default workflow is still usable without extra provider keys, so this page is mainly for cases where you want broader coverage or specific provider features.

### Model Settings

Use this page to choose how the assistant should operate.

Typical tasks here include:

- switching between cloud and local mode
- searching for available models
- assigning model roles
- checking local model connectivity
- refreshing available local models
- pulling a model when needed

If you are not sure what to change, keep the defaults and return to the workspace. Most users only need this page when they want to change behavior or connect a local model.

## Good Ways To Work

The app works best when you start broad and then narrow down.

1. Ask for the general location first.
2. Review the result.
3. Add a follow-up request to narrow the view or focus on a specific layer.
4. Repeat until the result is useful for your task.

This approach is usually better than trying to specify everything in the first message.

## If Something Does Not Look Right

The most common issues are straightforward.

- If nothing happens, make sure the app is actually running.
- If local model behavior looks wrong, check the model settings page.
- If an external provider is not available, review the access configuration.
- If the app seems to be holding onto an old result, start a fresh request in the workspace.

For more help, see:

- [Quick Start](./assets/docs/user/quick_start.md)
- [Workflows](./assets/docs/user/workflows.md)
- [Troubleshooting](./assets/docs/user/troubleshooting.md)

## For Local Setup

If you are setting the project up locally, the repository includes platform-specific startup and packaging scripts.

The shortest path on Windows is:

```cmd
copy /Y settings\.env.local.example settings\.env
start_on_windows.bat
```

For other platforms and for packaging details, use the startup and maintenance scripts already included in the repository. The technical documentation under `assets/docs` covers the deeper setup and runtime behavior.

## Project Contents

The repository is split into a few broad areas:

- `app/server` for the backend
- `app/client` for the frontend and desktop host
- `app/resources` for local data and supporting files
- `app/tests` for automated checks
- `settings` for environment-specific configuration

## License

This project is licensed under the MIT License. See `LICENSE` for the full text.
