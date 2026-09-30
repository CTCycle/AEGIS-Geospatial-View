# Current quality checks

- Backend focused regressions before the browser-scope fix: 74 passed.
- Additional post-fix scope/render regressions: 64 passed.
- Backend unit suite: 1,034 passed; 2 existing dependency deprecation warnings.
- Angular production build: passed.
- Karma: 264 passed; Angular Karma builder deprecation warning only, plus the
  existing sanitized-HTML and fixture `/x` warnings.
- Ruff: passed.
- Strict Pyright: 0 errors, 0 warnings, 0 informations.
- Strict production manifest audit: 86 manifests, 0 errors, 0 warnings.
- Browser-authoritative RainViewer acknowledgment: passed; 90 non-transparent
  pixels at z6 with source/layer/viewport/intersection checks satisfied.
- Cleanup: temporary browser tab closed, viewport override reset, listeners on
  ports 5011 and 5079 stopped, and the marked disposable runtime removed.
- QA JSON artifacts: parsed successfully.
