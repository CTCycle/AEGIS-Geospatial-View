# Isolated dataset-ingestion sub-slice

Date: 2026-09-30
Source boundary: `develop@889066b3`. This is a bounded Tier 4A candidate
check, not a promotion of any grouped T4A campaign ID.

## Execution

The existing local CSV and GeoJSON fixtures were executed through the real
ingestion services using a disposable pytest workspace under
`runtimes/cache/pytest-tmp/codex-20260930-ingestion`; no external credentials
or normal runtime data were used.

```text
cd app/server
.venv\\Scripts\\python.exe -m pytest -c pyproject.toml \\
  ..\\tests\\unit\\test_geospatial_ingestion.py \\
  ..\\tests\\unit\\test_geospatial_materialization_runner.py -q \\
  --basetemp=..\\..\\runtimes\\cache\\pytest-tmp\\codex-20260930-ingestion
```

Result: `10 passed in 0.53s`.

The executed cases covered CSV normalization, GeoJSON normalization and
invalid-geometry dropping, checksum and checksum-file verification, minimum
feature and bbox validation, spatial/text/tile index creation, source-health
records, and materialization filtering by capability ID.

## Boundary

The deterministic fixture path is healthy, but the grouped T4A IDs still lack
an authoritative one-to-one mapping in the campaign strategy. This run did
not validate a configured external dataset, browser rendering, or a production
rollback/cleanup contract after a failed materialization. It therefore remains
supporting evidence only; no T4A campaign slice is promoted to `PASS`.
