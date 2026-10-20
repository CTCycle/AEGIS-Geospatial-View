# Intent-driven discovery: limitations follow-up (2026-10-20)

This follow-up addresses the limitations recorded in
`../2026-10-20-intent-driven-discovery/report.md`.

- Branch: `intent-driven-discovery`.
- Exact lane: `opencode-go / deepseek-v4.1-flash`.
- Isolated runtime: `runtimes/cache/test-runtime/intent-discovery-20261020`.
- Servers: backend `127.0.0.1:5087`, client `127.0.0.1:4587`.
- Driven through the built-in browser.
- The servers and the browser pane were stopped afterwards, and both ports were verified free.

## Limitation → change

| Limitation | Change | Commit |
| --- | --- | --- |
| Region boxes over-cover (Europe includes North Africa and Turkey) | Macro regions list their member countries. Sampling masks the bbox with simplified Natural Earth 1:50m shapes. Seismic events are kept within 0.5° of member countries. | `73219e9a`, `d0cd76fe` |
| Sea points dropped by an elevation-zero test | A geometric land mask with a 0.05° coastal buffer replaces the heuristic, so sea cells are never requested. | `73219e9a` |
| Grid misses local extremes; World spacing about 25° | Grid densifies up to a 300 land-point budget, in batches of 100. A 3×3 refinement at one third of the spacing runs around the 5 strongest cells per metric. World spacing is now 8.57°. | `73219e9a` |
| USGS counts outside the US are lower bounds | Added an `emsc_earthquakes` provider (EMSC SeismicPortal FDSN). `preferred_bbox` ranks it first in Europe, the Mediterranean and the Middle East. | `436b66f6` |
| Open-Meteo values are model estimates | Kept and disclosed (user decision): no keyless gridded observation source exists. | — |
| Result points carry coordinates only | Up to 10 leading coordinate-only results get the nearest Nominatim place name; answers say "near ...". | `b9a49173` |
| Visual-clue image upload deferred | The composer can attach an image. `POST /api/chat/attachments` stores it, `run.start` passes `attachment_id`, and every model call of the run carries the image for vision models. | `d88c0262`, `1536ddec` |
| Paris zooms to street level on one weather point | `fit_evidence` widens the fit to a minimum 0.25° span, which is city scale. | `41c6339f` |
| (found live) Ordinal "7e" did not match Nominatim's "7th" | The resolver's matching normaliser collapses ordinal suffixes. | `ea49f441` |

## Live results

### Europe: where did it rain most today

- `completed`; screenshot `europe-rain.jpg`.
- 359 land points: 299 coarse at 2° plus 60 refined. 404 out-of-region points were excluded.
- The top 5 results are labelled ("near Bédouès-Cocurès, France").
- The answer disclosed that values are model estimates and that this is a sampled maximum.

### European seismic hotspots, past week

- `completed`; screenshot `europe-seismic-emsc.jpg`.
- EMSC was selected, returning about 700 events for the week. The same bbox and week returned 3 events from USGS (direct provider call).
- First run, before the fix: the top cells were in Anatolia.
- After `d0cd76fe`: 358 out-of-region events were excluded, and the top cells were in France, Spain and Switzerland. The completeness note was quoted.

### Where in the world is it hottest

- `completed`; screenshot `world-heat.jpg`.
- 345 land points: 8.57° coarse grid, 2.86° refinement. 572 points were excluded.
- Results are labelled as being in Mali, Brazil and the Central African Republic.

### Show the current weather in Paris on the map

- `completed`; screenshot `paris-weather-city-fit.jpg`.
- The map fits at city scale. Before the fix it zoomed to street level.
- The plain prompt "What's the weather in Paris?" answered as text with no map; that is the model's choice and unchanged behaviour.

### Image upload: "Where was this photo taken?"

- `completed`; screenshots `image-attachment-chip.jpg` and `image-visual-clue-result.jpg`.
- The test image was a canvas-drawn Paris street sign reading "7e Arrt / Avenue Gustave Eiffel". No external image was downloaded.
- The model read the sign and named the cues (signage, script).
- The first run asked for clarification because the resolver rejected the correct Nominatim candidate on the "7e"/"7th" mismatch. After `ea49f441` the street resolved and the map centred on it, with a caveat that the camera position is approximate.
- The attachment chip did not render right after "Start new chat" until `1536ddec`, which adds explicit change detection.

### Not run live: non-vision model with the attach button

- The disabled state is covered by a Karma spec.
- The server-side "cannot view images" note is covered by unit tests.

## Checks

- Backend unit: `1191 passed` (`unit-final.log`).
- Ruff clean (`ruff.log`).
- Pyright on the changed server files: 0 errors (`pyright.log`).
- Client Karma: `293 SUCCESS` (`frontend-specs.log`).
- `ng build` OK (`client-build.log`).
- `app/shared/openapi.json` regenerated for the attachment endpoint and fields.

## Remaining limitations

- Open-Meteo values are model estimates, and sampling can still miss extremes between samples.
- Earthquake catalogs remain incomplete below their completeness magnitude.
- The 1:50m masks approximate small islands and fine coastlines.
- Attached images live only in the in-memory store (900 s TTL) and are lost on restart. Only one image is allowed per request.
- Only one model lane was exercised.
