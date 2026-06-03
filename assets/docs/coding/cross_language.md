# Cross-Language Rules

Last updated: 2026-06-02

## Shared Rules

- Keep backend Pydantic contracts and frontend TypeScript contracts synchronized.
- Prefer scoped, additive changes over broad refactors.
- Remove dead code and obsolete artifacts when identified.
- Avoid duplicated logic across layers when a shared contract can serve both.
- Keep `assets/docs` updated whenever behavior or conventions change.
- Add new static catalog/reference data under `app/resources/catalog/reference`, not Python constants.
