# Experience And Accessibility

Last updated: 2026-08-20

## Core User Journeys

- Ask a geospatial question, receive an assistant response, and inspect map session output.
- Review geodata to understand layers, tools, providers, and access constraints.
- Open Access configurations to add optional provider keys.
- Open model settings to choose the agent model and manage provider credentials.

## Interaction Rules

- `Enter` submits chat.
- `Shift+Enter` inserts a newline.
- Loading states must be explicit.
- Error states should use actionable human-readable text.

## Loading And Empty States

- Workspace shows welcome or idle content before the first successful turn.
- Settings shows explicit empty-state UI when no filtered model results exist.

## Desktop Usability

- The supported viewport is a standard desktop or laptop browser window at
  least `1024px` wide.
- Below that width, the application shows a blocking minimum-size notice and
  preserves the desktop interface behind an inert shell.
- Workspace collapsing and constrained mouse resizing remain available.
- Prefer information density, horizontal space, and stable desktop navigation
  over mobile-specific stacking or touch-first interactions.

## Accessibility

- Maintain keyboard navigability for all controls.
- Preserve `:focus-visible` outlines.
- Maintain semantic containers and labels for form elements.
- Keep exactly one `main` landmark in the routed application shell.
- Modal dialogs must receive focus on open, trap Tab and Shift+Tab, close with Escape, and restore focus to the invoking control.
- Do not encode status solely by color.
- Respect reduced-motion preferences.

## Design Principles

- consistency
- clarity
- predictability
- simplicity
- usability-first
