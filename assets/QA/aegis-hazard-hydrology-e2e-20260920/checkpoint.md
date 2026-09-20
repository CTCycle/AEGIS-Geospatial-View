# AEGIS hazard/hydrology E2E rerun checkpoint

Checkpoint closed: 2026-09-20.

Follow-up evidence is in [report.md](report.md).

- Branch: `loop-dev`
- Source commit tested: `84c210f6`
- Provider/model lane: `opencode-go / deepseek-v4.1-flash`
- Post-fix focused regression set: `54 passed in 1.42s`
- Ruff: passed
- GEO-HYD-01: PARTIAL; FEMA raster retrieval/descriptor works, browser source
  loading still fails.
- GEO-HYD-05 and GEO-HYD-06: BLOCKED behind the unverified FEMA raster map.
- GEO-HYD-07: current rerun inconclusive after repeated invalid tool calls;
  prior guardrail PASS remains historical evidence only.
- GEO-HYD-08: PASS; Portland hydrography replacement and keep-only behavior
  rendered successfully.
- App processes stopped; ports `7059`, `4512`, and `9876` are free.
- No push was performed. The ACL-protected untracked `app/tests/cache/` tree
  remains preserved.
