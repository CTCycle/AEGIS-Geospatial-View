# T1-06 exact-head hosted-CI result

- Workflow: `CI`, event: `push` to `develop`
- Tested implementation commit: `af663adaa5e14be3fcd7312e4bd230cca11f1b40`
- Overall result: `PASS`
- Run: [GitHub Actions run 35845587545](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35845587545)

| Job | Result | Detail |
| --- | --- | --- |
| `backend-unit-tests` | `PASS` | Static analysis, source compilation, isolated Alembic checks, corrected 397-test backend selection, and shared OpenAPI diff all passed. |
| `frontend-build-and-tests` | `PASS` | Frontend state tests, production build, unit tests, and geospatial browser smoke passed. |
| `capability-contract-validation` | `PASS` | Manifest, schema, provider/API, runtime-profile, and tool-binding checks passed. |
| `persistence-conformance` | `PASS` | SQLite persistence conformance passed. |

All four jobs passed on the exact pushed implementation commit. GitHub emitted
non-failing runner/action deprecation and future-image notices. The earlier
failed run on `fccafa1f48be71a8f68116b83783b29369e9e419` remains historical; its
stale test target is removed in the tested implementation commit.
