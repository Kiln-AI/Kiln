---
status: complete
---

# Implementation Plan: Experiment Lineage Page

## Phases

- [x] Phase 1: Shared chart palette and lineage logic. Add `chart_palette.ts` and set it on the two Compare charts, as its own commit. Add the link helpers in `link_builder.ts`. Add the pure modules under `lib/utils/lineage/` (graph, changes, glyph, layout, viewport, navigation, display), the test fixtures, and every unit test the architecture lists. No page yet.
- [ ] Phase 2: The Experiment Lineage page. Add the route, the glyph and swatch components, the canvas (toolbar, zoom and pan, hover, keyboard, selection), the filter chips, the stats row, the detail panel, and the loading, error and empty states. Add the component tests, then do the visual and 1,000-node checks from the architecture.
- [ ] Phase 3: Entry points. Add the "Experiment Lineage" button and the "Show in Experiment Lineage" row item on the Optimize page, and the AppPage button on the Compare page. Run docs-sync.
