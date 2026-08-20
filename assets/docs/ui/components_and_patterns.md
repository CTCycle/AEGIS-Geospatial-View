# Components And Patterns

Last updated: 2026-08-20

## Reusable Components

- `map-preview.component.*`
- `settings-icon-action.component.*`
- `settings-modal-shell.component.*`
- `settings-api-key-field.component.*`
- `selected-model-summary.component.*`
- `chat-message.component.*`
- `capability-status-list.component.*`
- `source-health-badge.component.*`
- `camera-popup.component.*`
- `overlay-controls.component.*`

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
- Describe a cloud agent as configured until a live request succeeds. Mark it verified after a successful run and needs attention after a terminal run error; never infer live provider readiness from stored credential health or model-catalog access alone.
- Settings dialogs move focus inside on open, trap keyboard focus, close with Escape, and restore focus to their opener.
- Keep chat input within the realtime contract's 12,000-character message limit before sending.
- Treat normalized backend render descriptors as the only source for raster and
  provider-native map layers; component code must not reconstruct provider URLs.
- Validate Operations Bar navigation, routed layouts, map controls, and text
  wrapping at supported desktop widths after significant UI edits. Validate the
  minimum-size gate below `1024px` instead of a mobile layout.
