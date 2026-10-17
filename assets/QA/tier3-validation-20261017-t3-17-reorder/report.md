# T3-17 manual overlay ordering follow-up

Date: 2026-10-17
Status: `PASS`
Branch: `validation`
Tested source: `7dc62147219bd84ef259b4826c10ead9dfa3fadf` plus the scoped working-tree changes recorded in this commit.
Browser: Codex in-app Browser at `http://127.0.0.1:5079/`
Agent lane: `opencode-go / deepseek-v4.1-flash` (isolated runtime probe passed; no model substitution).

## Result

The T3-17 lifecycle passed with Open-Meteo pressure/humidity/wind points, NASA
GIBS MODIS Terra daytime land-surface-temperature raster, and a bounded GBIF
occurrence sample around Rome. The browser showed all three attributed layers,
and the backend recorded ready `render_observed` acknowledgements with sources,
layers, and viewport checks satisfied. Raster acknowledgements reported 21,584
nontransparent pixels; the GBIF layer loaded 300 records and rendered three
clusters.

Keyboard-accessible **Move up** and **Move down** controls changed the order
from Open-Meteo / MODIS / GBIF to Open-Meteo / GBIF / MODIS and back. The map
visibly changed with the order: the GBIF clusters appeared above the raster
when moved up and were occluded when moved below the fully opaque raster. The
first layer's up control and last layer's down control were disabled. Each move
announced its resulting position. Independent opacity changes to 80%, 50%, and
30% were observed for Open-Meteo, MODIS, and GBIF, respectively; all three were
restored to 100%.

Removing MODIS retained Open-Meteo and GBIF in their existing order. Re-adding
MODIS preserved those survivors and appended the new raster. Removing GBIF then
retained the visible Open-Meteo and MODIS layers. This completed both selective
removal directions and verified retained order across map updates.

An earlier raster re-add request reached its configured execution limit. The
same conversation was resumed on the same exact provider/model lane; a fresh
raster retrieval completed after one backend validation retry, and the later
GBIF removal completed normally. No alternate model was used.

## Evidence and checks

- [Sanitized live run and render-ack evidence](run-evidence.json)
- [Browser interaction record](browser-evidence.md)
- [Isolated exact-lane probe metadata](runtime/live-runtime.json)
- Focused Karma suites: `176 SUCCESS`.
- Production client build: `npm run build -- --no-progress` passed.
- Browser visual state was inspected during the run. The in-app Browser
  screenshot API returned `Unable to capture screenshot`, so this report keeps
  the directly observed accessible state and sanitized render trace rather
  than a screenshot file.

The exact lane probe resolved the configured credential only inside the
isolated runtime. No credential value is included in this evidence. The runtime
and isolated database were stopped and removed after evidence collection; the
cleanup record is in [runtime-cleanup.json](runtime-cleanup.json).

Hosted CI is recorded separately from this local/browser report after the
scoped change is pushed.
