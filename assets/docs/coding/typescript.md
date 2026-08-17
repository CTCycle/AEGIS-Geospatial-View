# TypeScript

Last updated: 2026-08-17

## Baseline

- Angular 22 standalone architecture
- TypeScript strict mode
- Shared frontend contracts live in `app/client/src/app/core/types.ts`
- Backend calls route through `app/client/src/app/core/api.ts`

## Typing And Data Safety

- Avoid `any`.
- Prefer explicit interfaces and narrowing from `unknown`.
- Validate response shape before rendering.
- Keep shared payload contracts centralized.
- Use `core/realtime-parsers.ts` as the typed boundary for realtime envelopes,
  run-event discriminators, sequence/version fields, visibility, JSON payloads,
  and normalized terminal fields. Optional malformed data must not overwrite
  valid page state.
- Keep intentionally open-ended provider metadata as `JsonValue` or `unknown`;
  concrete responses such as `OllamaHealthResponse` should type their known
  fields explicitly.

## Component And State Design

- Keep route orchestration in `pages/*`.
- Keep reusable presentational blocks in `components/*`.
- Keep API and shared state utilities in `core/*`.
- Represent async UI state explicitly.
- Parse `unknown` API payloads through the shared parser/type-guard boundary;
  keep run event IDs and context revisions when applying replayed responses.
- Keep dynamic provider narrowing and model-library merging in
  `core/model-library.ts`; pages retain API calls and settings orchestration.
- Reusable markup that must preserve an existing semantic host may use a typed
  attribute-selector standalone component, as with the settings warning
  section.

## UX And Accessibility Coding

- Implement explicit loading, empty, and error states.
- Preserve keyboard access and visible focus behavior.
- Use semantic HTML.
- Do not rely on color alone to convey meaning.
- Render backend map and provider errors as explicit unavailable or warning
  states; never create a visible layer from a failed provider response.
