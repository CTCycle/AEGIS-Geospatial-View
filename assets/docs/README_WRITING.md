# README Writing Guidelines

Last updated: 2026-03-28

Use this structure for project README files in this repository.

## 1. Overview

State:
- what the project does
- problem it solves
- high-level architecture (frontend, backend, data flow)

Keep this user-facing. Do not document internal class/function details.

## 2. Installation

Document reproducible setup paths:
- Windows launcher flow (`AEGIS/start_on_windows.bat`)
- any manual setup path if needed

Include only required prerequisites and concise commands.

## 3. How To Run

Provide:
- app startup command(s)
- frontend URL
- backend docs URL (`/docs`) when applicable

## 4. How To Use

Describe operational workflow from user perspective:
- what inputs users provide
- what outputs users receive
- key UI screens and actions

If screenshots are included, use repository assets and short captions.

## 5. Testing

Document the canonical test flow:
- primary: `tests/run_tests.bat`
- optional manual pytest invocation

## 6. Configuration

Document configuration sources and behavior:
- `AEGIS/settings/.env`
- `AEGIS/settings/configurations.json`

Include a concise variable table.

## 7. Resources and Data

Explain important resource directories and their purpose (for example logs, DB file, templates).

## 8. Maintenance Commands

List operational scripts and what they do (not full script internals).

## 9. License

State the license and reference the license file.

## Quality Checklist

A good README is:
- accurate to current code
- concise and skimmable
- user-oriented, not implementation-heavy
- consistent with `assets/docs` terminology and runtime assumptions
