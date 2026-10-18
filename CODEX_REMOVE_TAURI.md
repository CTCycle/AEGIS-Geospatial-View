You are working on the AEGIS-Geospatial-View repository checked out at the current directory.

TASK: Remove all Tauri packaging infrastructure, consolidate the launcher scripts into a single PowerShell menu, and update all documentation. Do NOT modify any Python, TypeScript, or Angular source code.

## Note: This repo does NOT have an app/src-tauri/ directory — only the Tauri build scaffolding exists.

## Step 1: Create `app.ps1` at repo root

Replace both `start_on_windows.bat` and `setup_and_maintenance.bat` with a single `app.ps1` interactive menu.

Menu title: "AEGIS — Geospatial View"

The menu options and logic are identical to PROMPT 1 Step 1. Read the existing batch files in this repo for exact paths, ports, and defaults.

## Step 2: Delete old batch files

- start_on_windows.bat
- setup_and_maintenance.bat

## Step 3: Delete Tauri scaffolding

Directories to delete (entire trees):
- release/tauri/ (build_with_tauri.bat, scripts/clean-tauri-build.ps1, scripts/export-windows-artifacts.ps1)
- release/windows/ (if exists)

Files to delete:
- .github/workflows/desktop-release.yml
- settings/.env.local.tauri.example

IMPORTANT: Leave .github/workflows/geospatial-live-smoke.yml untouched — it's not Tauri-related.

## Step 4: Update .gitignore

Remove any Tauri entries.

## Step 5: Update README.md

Read the current README.md and make these changes:
- Remove the "app/src-tauri for the desktop shell and packaging config" bullet from the structure listing
- Remove the entire "Desktop Artifact Hygiene" section (lines about versioned src-tauri and release/windows)
- Remove any other Tauri/desktop/packaging references
- Update batch file references to app.ps1

## Step 6: Update assets/docs/

Scan for any Tauri references.

## Step 7: Verify

Check: release/tauri/ gone, .env.local.tauri.example gone, desktop-release.yml deleted, app.ps1 exists.