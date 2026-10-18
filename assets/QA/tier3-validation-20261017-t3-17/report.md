# T3-17 mixed raster/vector continuation

Last updated: 2026-10-17

**PARTIAL.** Mixed raster/vector rendering, independent opacity changes, and
selective raster removal pass. A non-empty third vector partner, reverse
vector-removal retention, and ordering remain unproven. No complete T3-17 pass
or broader routing/provider guarantee is claimed.

## Tested boundary

Branch `validation`, base `7faf0c1e778c7cf19f6f55177002e079f29a9733`, with
the pending T3-16/T4-04 source repairs and the raster visibility change recorded
in [slice.json](slice.json). Existing `app/server/.venv`, rebuilt production
Angular client, and Codex in-app Browser. No worktree or dependency install.
The disposable backend on `127.0.0.1:5079` persisted exactly
`opencode-go / deepseek-v4.1-flash` through Settings; its structured probe
passed with complete parsing. No provider/model substitution.

## Results and remediation

1. Open-Meteo atmospheric points rendered around Rome. Adding the explicit
   `MODIS_Terra_Land_Surface_Temp_Day` raster reproduced
   `raster_zoom_unsupported` twice while the vector remained visible.
2. The renderer applies `max_zoom` to the raster **source**; MapLibre can
   overzoom its highest-resolution tile. The visibility probe incorrectly
   rejected the higher map zoom before fetching that tile. It now probes the
   capped source tile, retaining minimum-zoom rejection and decoded-pixel,
   viewport-intersection, loading, layer, and visibility checks. Regression
   coverage verifies overzoom selection and rejection below source minimum.
3. A retry using previously saved evidence proved 21,584 raster pixels and
   one vector feature, but failed backend `required_data_retrieved` and
   `spatial_scope_applied` checks. It is **not** an accepted render. Fetching
   fresh GIBS evidence then passed the same two-layer composition with a
   matching ready observation, source/layer checks, and both attributions.
   Accepted run: `run_84900194d3824f82bb80a9e3b25f38bf`, candidate
   `candidate-0e2232310d46405c86cb76c59b8720cc`, revision `2`.
4. The browser displayed both GIBS raster pixels and the Rome point. Independent
   keyboard opacity changes produced 1% raster / 99% vector; restoring raster
   opacity to 100% preserved both controls. See [mixed map](captures/mixed-final.jpg)
   and [opacity controls](captures/opacity.jpg). Opacity is client-local;
   these UI operations do not create native acknowledgement events.
5. Third-layer attempts remain incomplete: GBIF discovery failed twice,
   including an explicit-ID retry; USGS earthquakes within 300 km returned
   valid-empty and retained the two existing layers with an accepted ready
   observation; the POI request resolved an unrelated Ankara landmark and
   exhausted invalid tool calls. These are routing/tool and valid-empty
   boundaries, not proof of three rendered layers or provider outages.
6. Removing only MODIS completed with an accepted ready observation and
   retained Open-Meteo at Rome (`1 of 1 visible`). See
   [selective removal](captures/raster-removed.jpg). A subsequent fresh-raster
   re-add failed discovery; reverse vector removal and ordering were therefore
   not validated. The last good vector map remained visible.

[Run evidence](run-evidence.json) retains bounded public trace fields, map
identities, requirements, observations, and failures, without raw checkpoints
or private reasoning. The capture helper accumulates runs because the snapshot
API exposes only the latest eight. The initial atmospheric/IMERG discovery
runs aged out before accumulation was enabled; their behavior is described
above without claiming a retained full trace. Both original MODIS zoom failures
and the final accepted mixed-stack/removal observations are retained.

## Verification

- Backend: **1,088 passed**, two existing upstream warnings; [log](backend-unit.log).
- Changed backend files: Ruff PASS; [log](ruff.log).
- Complete strict backend Pyright: **0 errors/warnings/informations**; [log](pyright.log).
- Raster visibility and map rendering frontend suites: **33 passed**; [log](frontend-tests.log).
- Production client build: PASS; [log](frontend-build.log).
- Browser warning/error buffer returned no entries at final capture. No
  independent HAR/network-cleanliness claim.
- An initial pytest invocation rejected a noncanonical cache path; the next
  hit pre-existing protected temporary residue. The successful run used the
  canonical cache and a fresh child beneath `runtimes/cache/pytest-tmp`, without
  deleting that residue. Failed setup output was replaced by the successful log.

The pending T3-16/T4-04 repairs and curated evidence remain separately scoped in
their [report](../tier3-validation-validation-20261017-t3-16/report.md).
The campaign is now **43 PASS / 3 PARTIAL / 2 BLOCKED / 20 UNRUN**.
Hosted CI is a separate post-push boundary; this report claims local validation.

## Cleanup and continuation

Stop the keeper through its STOP marker and verify port 5079 and its owned
runtime are removed. Final cleanup and source fingerprints are in
[slice.json](slice.json). Canonical Settings/database content is not edited by
the validation requests; the keeper reads its credential in-process. A live
canonical database file lock prevented a before-cleanup file hash, so no
paired database-integrity hash claim is made.

Continue T3-17 with a reliable non-empty third vector partner and both removal
directions/ordering. Preserve the backend evidence checks; visible raster
pixels alone do not close an unaccepted candidate. T3-15 remains deferred on
the retired EEA service, and T3-18 remains UNRUN.
