# Cross-Language Rules

Last updated: 2026-08-18

## Shared Rules

- Keep backend Pydantic contracts and frontend TypeScript contracts synchronized.
- Prefer scoped, additive changes over broad refactors.
- Remove dead code and obsolete artifacts when identified.
- Avoid duplicated logic across layers when a shared contract can serve both.
- Keep `assets/docs` updated whenever behavior or conventions change.
- Add new static catalog/reference data under `app/resources/catalog/reference`, not Python constants.
- Keep JSON-shaped contracts object-safe at the Python/TypeScript boundary;
  validate unknown API payloads before rendering or persisting them.
- Treat provider and visualization warnings as first-class response data. Do
  not infer success from a non-empty trace, an HTTP 200 wrapper, or a failed
  upstream request.

## OpenAPI Contract

- `app/shared/openapi.json` is generated from `server.app:app` and is the
  shared backend/frontend API contract.
- Regenerate it with `python app/scripts/generate_openapi.py` after changing
  an API route or Pydantic contract.
- Keep the generated file synchronized with the runtime schema; do not edit it
  manually.
