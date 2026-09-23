# T1-03 exact-head hosted-CI result

- Workflow: `CI`, event: `push`
- Tested commit: `fccafa1f48be71a8f68116b83783b29369e9e419`
- Overall result: `FAIL`
- Run: [GitHub Actions run 35834459171](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35834459171)

| Job | Result | Detail |
| --- | --- | --- |
| `persistence-conformance` | `PASS` | SQLite persistence conformance completed. |
| `frontend-build-and-tests` | `PASS` | Frontend state tests, production build, frontend unit tests, and geospatial browser smoke passed. |
| `capability-contract-validation` | `PASS` | Manifest, schema, provider/API, runtime-profile, and tool-binding checks passed. |
| `backend-unit-tests` | `FAIL` | Static analysis, compilation, and migration metadata passed; the `Run backend unit suites` step exited 4 before collecting tests because the command includes missing path `app/tests/unit/services/search`. The follow-up shared OpenAPI check was skipped. |

This is a workflow-path failure, not a failed T1-03 conversation assertion. T1-03 remains `PASS` for its local focused suites and browser scenarios. Hosted CI remains `FAIL` until the configured test path is corrected and the exact pushed head passes.
