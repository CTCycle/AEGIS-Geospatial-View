# T0-04 Windows startup evidence

Status: `PASS`

## Boundary

- Branch: `develop`
- Starting HEAD: `7e8b10d58aebf21f194a74bcc2307f9d8e08f15c`
- Validated source commit: `afa608c8d5c53a34d0ce8da36e5fe5f47f689145`
- Validation source: working tree based on that exact HEAD.
- Host: Windows PowerShell/PowerShell 7, Python 3.14, Node 22.23.1,
  Chrome Headless 153.
- Isolated application data: `runtimes/cache/test-runtime/tier0-validation-develop-20260922`
- All pytest basetemp/cache output stayed below `runtimes/cache/pytest-tmp` and
  `runtimes/cache/pytest`.

## Coverage and result

The existing dated startup report remains the evidence for clean/warm launch,
dependency/build reuse and repair, explicit install/rebuild paths, occupied
port consent/decline, multi-port ownership, SQLite no-op startup, browser
readiness, and final cleanup. The current revision closed and reran the gaps
from that report:

- protected or unresolved owner identity fails closed before prompt/termination;
- non-interactive occupied-port handling fails without termination;
- port ownership/PID reuse is revalidated before termination;
- taskkill refusal remains a visible failure;
- backend and frontend readiness failures clean only launcher-owned processes;
- dynamic provider outage does not block isolated application startup;
- canonical cache roots and launcher AST/contract tests pass.

Current results:

```text
backend-focused final slice: 38 passed, 2 warnings, 3.58 seconds
frontend-state helper:       19 passed, 0 failed
launcher safety harness:     PASS
```

The final harness recorded launcher-owned PIDs for both readiness-failure
stages, unrelated PIDs surviving, simulated listener PIDs only, and
`real_services_or_user_processes_targeted=false`. Ports 7059, 4512, and 9876
were verified free afterward. No startup-performance improvement claim is made;
the earlier report's absence of a paired benchmark remains a limitation.

## Remediation

`Confirm-PortConflictTermination` now fails closed when a listener's process
name or start-time identity cannot be resolved. It does not prompt or terminate
an unresolved owner. The existing grouped consent, signature recheck,
deduplicated termination, and launcher-owned readiness cleanup behavior was
preserved.

The repository's six exact ignored obsolete cache roots were removed after
read-only path/ignore checks. They were not tracked source or user data.

## Evidence

- [final backend-focused log](backend-focused-retry.log)
- [frontend-state log](../final/frontend-state.log)
- [final launcher harness JSON](launcher-safety-harness-final.json)
- [launcher harness source](launcher-safety-harness.ps1)
- [historical startup optimization report](../../startup-optimization-20260922/report.md)
