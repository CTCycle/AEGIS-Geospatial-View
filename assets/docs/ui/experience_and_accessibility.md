# Experience And Accessibility

Last updated: 2026-06-02

## Core User Journeys

- Ask a geospatial question, receive an assistant response, and inspect map session output.
- Review geodata to understand layers, tools, providers, and access constraints.
- Open Access configurations to add optional provider keys.
- Open model settings to manage provider and role assignments.

## Interaction Rules

- `Enter` submits chat.
- `Shift+Enter` inserts a newline.
- Loading states must be explicit.
- Error states should use actionable human-readable text.

## Loading And Empty States

- Workspace shows welcome or idle content before the first successful turn.
- Settings shows explicit empty-state UI when no filtered model results exist.

## Responsiveness

- The app must remain usable on desktop and narrow widths.
- Workspace supports collapsing toolbar and constrained resize behavior.
- Settings adapts from multi-column to narrow layouts.
- Avoid fixed heights that break small-screen scrolling.

## Accessibility

- Maintain keyboard navigability for all controls.
- Preserve `:focus-visible` outlines.
- Maintain semantic containers and labels for form elements.
- Do not encode status solely by color.
- Respect reduced-motion preferences.

## Design Principles

- consistency
- clarity
- predictability
- simplicity
- usability-first
