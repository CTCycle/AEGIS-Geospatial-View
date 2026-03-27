# UI/UX Audit Report (Pre-Implementation)

Date: 2026-03-27  
Scope: `AEGIS/client/src` frontend codebase

## 1) Discovery Summary

### Project structure and primary screens
- App shell: `AEGIS/client/src/App.tsx`
- Primary screen: `AEGIS/client/src/pages/GeospatialPage.tsx`
- Secondary screen: `AEGIS/client/src/pages/DatabaseBrowserPage.tsx`
- Navigation: `AEGIS/client/src/components/Sidebar.tsx`
- Shared UI components: `AEGIS/client/src/components/*`
- API layer: `AEGIS/client/src/services/api.ts`

### Routing model
- No URL router library; page switching is local state (`activePage`) in `App.tsx`.

### Styling approach
- Plain CSS files imported per component/page.
- Global styles in `AEGIS/client/src/index.css`.
- App-level layout styles in `AEGIS/client/src/App.css`.
- No design token system (CSS variables for spacing/type/color are not centralized).

### Repeated styling and duplication signals
- Repeated class names across files with overlapping semantics:
  - `.panel-title`, `.panel-description`, `.form-group`, `.helper-text`, `.empty-state`
- Repeated hardcoded color values across many files (`#0f172a`, `#475569`, `#cbd5e1`, `#2563eb`, etc.)
- Repeated hardcoded radii (`8px`, `10px`, `12px`, `14px`, `16px`) and spacing values.

### Inline styles / hardcoded values
- Inline styles detected in `AEGIS/client/src/components/MapPreview.tsx` (`border`, transform scale).
- Many fixed `px`/absolute constraints in CSS (including `min-height: 560px` on map iframe).

## 2) Systematic Issue Report

## App Shell / Navigation

### [Critical] Navigation pattern does not match required frozen top tab navbar
- Files:
  - `AEGIS/client/src/App.tsx`
  - `AEGIS/client/src/components/Sidebar.tsx`
  - `AEGIS/client/src/components/Sidebar.css`
  - `AEGIS/client/src/App.css`
- Root cause: Left icon sidebar is the only navigation shell, with fixed left margin coupling (`margin-left: 72px`).
- Minimal fix: Replace sidebar with fixed top tab navigation container and remove left-margin-coupled layout.
- Classification: Structural improvement

### [High] Navigation includes deprecated Database Browser destination
- Files:
  - `AEGIS/client/src/App.tsx`
  - `AEGIS/client/src/components/Sidebar.tsx`
  - `AEGIS/client/src/pages/DatabaseBrowserPage.tsx`
  - `AEGIS/client/src/context/DatabaseBrowserContext.tsx`
  - `AEGIS/client/src/services/api.ts`
- Root cause: Data browser remains integrated in navigation and service layer.
- Minimal fix: Remove data browser page/context/API calls and all nav references.
- Classification: Structural improvement

## Geospatial Screen Layout

### [Critical] Screen layout does not satisfy required left-toolbar + right-canvas split (~70% canvas)
- Files:
  - `AEGIS/client/src/pages/GeospatialPage.tsx`
  - `AEGIS/client/src/App.css`
  - `AEGIS/client/src/pages/GeospatialPage.css`
- Root cause: Current structure uses stacked sections (`controls-row` then `visual-row`) rather than persistent two-pane layout.
- Minimal fix: Restructure page into two columns with explicit toolbar section and responsive canvas section using consistent width ratios.
- Classification: Structural improvement

### [High] Agentic panel occupies primary controls area
- Files:
  - `AEGIS/client/src/pages/GeospatialPage.tsx`
  - `AEGIS/client/src/components/AgenticSearch.tsx`
  - `AEGIS/client/src/components/AgenticSearch.css`
- Root cause: Agentic feature still treated as a first-class control panel.
- Minimal fix: Remove agentic panel and related state; keep only search controls in toolbar.
- Classification: Structural improvement

### [Medium] Map toolbar action semantics are unclear and duplicated
- Files:
  - `AEGIS/client/src/pages/GeospatialPage.tsx`
- Root cause: Both “Reset view” and “Reload overlays” call the same handler (`rerunLastSearch`).
- Minimal fix: Keep one clear action matching current behavior or differentiate actions if needed.
- Classification: Quick win

## Responsiveness and Overflow

### [High] Map iframe min-height can cause viewport overflow on smaller screens
- Files:
  - `AEGIS/client/src/components/MapPreview.css`
- Root cause: `height: 70vh` plus `min-height: 560px` is too rigid for small laptop/mobile viewports.
- Minimal fix: Use responsive clamp/min strategy and breakpoint overrides.
- Classification: Quick win

### [High] Main layout depends on fixed left offset and does not adapt to top-nav/mobile patterns
- Files:
  - `AEGIS/client/src/App.css`
- Root cause: `margin-left: 72px` and `max-width: calc(100% - 72px)` assume permanent left rail.
- Minimal fix: Move to top-offset content spacing and responsive column collapse.
- Classification: Structural improvement

## Typography and Hierarchy

### [Medium] Heading hierarchy is weak and inconsistent
- Files:
  - `AEGIS/client/src/pages/GeospatialPage.tsx`
  - `AEGIS/client/src/components/PanelHeader.tsx`
- Root cause: Primary heading is `h1`, while repeated panel titles are fixed `h3` regardless of document structure.
- Minimal fix: Normalize semantic hierarchy (use `h2` for major sections) and consistent scale tokens.
- Classification: Quick win

### [Low] Font stacks vary in component-specific blocks
- Files:
  - `AEGIS/client/src/components/StatsPanel.css`
- Root cause: `pre` element overrides global font family with long local fallback chain.
- Minimal fix: Use shared monospace/body tokens for consistency.
- Classification: Quick win

## Color and Tokenization

### [High] Color system is hardcoded and duplicated across components
- Files:
  - `AEGIS/client/src/index.css`
  - `AEGIS/client/src/App.css`
  - `AEGIS/client/src/components/*.css`
  - `AEGIS/client/src/pages/*.css`
- Root cause: No centralized color tokens; extensive one-off declarations.
- Minimal fix: Introduce shared CSS variables in `index.css` and migrate key components.
- Classification: Structural improvement

### [Medium] Inconsistent semantic coloring between screens/components
- Files:
  - `AEGIS/client/src/pages/DatabaseBrowserPage.css`
  - `AEGIS/client/src/components/LocationSearch.css`
  - `AEGIS/client/src/components/StatsPanel.css`
- Root cause: Components use different accent colors and contrast treatments without a single semantic map.
- Minimal fix: Normalize accent/success/error/focus tokens.
- Classification: Quick win

## Component Consistency

### [High] Shared classes are redefined in multiple component CSS files
- Files:
  - `AEGIS/client/src/components/AgenticSearch.css`
  - `AEGIS/client/src/components/LocationSearch.css`
  - `AEGIS/client/src/App.css`
- Root cause: Common class names with local style definitions create cascade collision risk and maintenance overhead.
- Minimal fix: Scope component-specific classes or consolidate shared primitives into one source.
- Classification: Structural improvement

### [Medium] Mixed button style conventions without shared primitives
- Files:
  - `AEGIS/client/src/App.css`
  - `AEGIS/client/src/components/LocationSearch.css`
  - `AEGIS/client/src/pages/DatabaseBrowserPage.css`
- Root cause: `ghost-button`, `primary-button`, `refresh-button`, `mode-tab` use divergent spacing/radius/state patterns.
- Minimal fix: Define consistent base button tokens and state styles.
- Classification: Quick win

## Interaction and Accessibility

### [Medium] Focus-visible styling is not consistently explicit across custom interactive controls
- Files:
  - `AEGIS/client/src/components/LocationSearch.css`
  - `AEGIS/client/src/pages/DatabaseBrowserPage.css`
  - `AEGIS/client/src/components/Sidebar.css`
- Root cause: Global focus style exists, but some custom controls rely only on default or hover-only feedback.
- Minimal fix: Add visible `:focus-visible` styles for all custom controls.
- Classification: Quick win

### [Low] Reduced-motion preference handling is absent
- Files:
  - `AEGIS/client/src/index.css`
  - `AEGIS/client/src/components/*.css`
- Root cause: Animations/transitions are always enabled.
- Minimal fix: Add `@media (prefers-reduced-motion: reduce)` fallbacks.
- Classification: Quick win

## Code Health / Dead UI

### [Medium] Unused UI modules likely remain as dead code
- Files:
  - `AEGIS/client/src/components/ConfigurationDrawer.tsx`
  - `AEGIS/client/src/components/ConfigurationDrawer.css`
  - `AEGIS/client/src/components/StatusOutput.tsx`
  - `AEGIS/client/src/components/StatusOutput.css`
- Root cause: Components are present but not used in app shell flow.
- Minimal fix: Remove if unused after reference validation.
- Classification: Quick win

## 3) Items Marked “Needs Verification”

- Exact contrast ratios for all text/background pairs (requires runtime measurement tooling).
- Keyboard tab order through full interactive flow after layout changes.
- Mobile viewport behavior for embedded map HTML payload across major browsers.

## 4) Proposed Implementation Order

1. Remove deprecated feature surfaces first (agentic + database browser) to reduce style noise.
2. Introduce shared tokens (spacing/type/color/radius/shadow) in global CSS.
3. Implement new fixed top tab shell and two-pane page layout.
4. Refactor shared component styles to consume tokens and unify states.
5. Apply responsive and accessibility refinements.
6. Re-run build/tests and residual-reference scans.
