# GEO-FOCUS-16 browser evidence

Date: 2026-09-28

Source boundary: `develop@87ca6942`

Lane: exact `opencode-go / deepseek-v4.1-flash`; no fallback or provider switch
was used. The local runtime used the disposable data root
`runtimes/cache/aegis-route-validation-20260928-01`, with backend `7059` and
frontend `4512`.

## PVGIS — PASS

The Codex in-app Browser submitted:

> Estimate PVGIS solar potential near Rome, Italy.

The visible response resolved Rome, selected **PVGIS Solar Potential**, and
reported **approximately 1,267 kWh/kWp/year**. It identified the source as
PVGIS / European Commission JRC, stated that the result is a metadata-only
point insight, and retained the catalog reliability caveat. The map remained
unprepared, which is correct for the direct-text capability.

The persisted evidence summary recorded:

```json
{
  "run_id": "run_7731b7c73cca4b9fbf5fac1f7fdaf0dd",
  "evidence_id": "evidence_620f318fa52a4c31ab82cacc79ef181d",
  "result_status": "ok",
  "result_type": "metadata",
  "solar_potential": {
    "yearly_kwh_per_kwp": 1267.38,
    "unit": "kWh/kWp/year"
  }
}
```

## EEA environmental noise — PARTIAL

The Browser first requested:

> Show environmental noise exposure around Milan, Italy.

The UI requested a location disambiguation. After selecting **Milan,
Lombardy, Italy**, the exact lane resolved the location, described
`eea_noise_2019`, and executed the EEA provider successfully. The persisted
provider evidence was `result_type=raster`, `result_status=ok`, with the
European Environment Agency attribution and a renderable descriptor.

The browser then prepared a map candidate, but MapLibre could not load the
public EEA raster source. The visible final state showed a blank map workspace,
the execution panel marked failed, and the message:

> Previous map render failed (`render_failed`) during maplibre: A map data source
> could not be loaded.

The run recorded an initial viewport-validation failure, one prepared map
candidate, a failed render observation, and subsequent schema/semantic-invalid
map-plan recovery calls. No raster pixels or accepted `map.render_ack` were
obtained. This is retained as a public-source/render boundary, not promoted to
a provider retrieval failure.

The screenshot was captured inline from the Codex in-app Browser. That browser
surface did not provide a local binary export, so no unverifiable screenshot
path is claimed here.
