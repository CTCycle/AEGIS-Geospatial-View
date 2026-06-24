# Components And Patterns

Last updated: 2026-06-22

## Reusable Components

- `map-preview.component.*`
- `model-role-actions.component.*`
- `settings-icon-action.component.*`
- `settings-modal-shell.component.*`
- `settings-api-key-field.component.*`
- `model-stats-panel.component.*`

## Interaction States

All interactive components must provide:

- default
- hover
- active or selected when applicable
- disabled
- focus-visible

## Controls

- Base form controls are normalized globally in `styles.css`.
- Component-level variants may specialize visuals but should preserve shared focus and disabled behavior.

## Feedback Patterns

- Use persistent status text for settings operations.
- Use inline alerts for map and session concerns.
- Keep progress indicators visible during in-flight chat requests.
- During active agent runs, keep the chat composer enabled. Additional messages are refinements for the active run and should use compact steering presentation.
- Render assistant messages as sanitized Markdown and user messages as escaped plain text.
- Keep agent availability shown as ready between requests; use run progress labels only while work is active.
- Validate Operations Bar navigation, routed layouts, map controls, and text wrapping at desktop and mobile widths after significant UI edits.
