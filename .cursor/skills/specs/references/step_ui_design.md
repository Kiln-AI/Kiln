# Step: UI Design

UI/UX design for projects with user-facing interfaces. Skipped for backend-only projects.

## Process

1. Read overview + functional spec
2. Propose UI structure
3. Iterative Q&A with user
4. Draft `ui_design.md`
5. Present for review
6. Iterate based on feedback
7. Confirm, mark `status: complete`

## What to Cover

Content varies by project type:

### Web Applications

- Page inventory: what pages exist
- Page layout: what's on each page
- Navigation: primary nav, secondary nav, breadcrumbs
- Component breakdown: reusable UI components
- Responsive behavior: mobile, tablet, desktop
- Overlays: modals, sidebars, slide-outs

### Mobile Applications (iOS/Android)

- Screen inventory: what screens exist
- Screen flow: how users navigate between screens
- Screen content: what's on each screen
- Navigation patterns: tabs, navigation stacks, modals, sheets, bottom sheets
- Platform conventions: follow HIG (iOS) or Material Design (Android)

### CLI Tools

- Command structure: subcommands, flags, arguments
- Output formatting: tables, JSON, human-readable
- Interactive prompts: confirmations, selections
- Help text: per-command, global flags

## UX Lens

Think like a senior designer:

- **Intuitive**: Can users figure it out without training?
- **Discoverable**: Can users find features without hunting?
- **Low cognitive load**: Is the interface simple, not overwhelming?
- **Progressive disclosure**: Show simple first, reveal complexity as needed
- **Platform conventions**: Don't reinvent standard patterns

Follow platform conventions. Users already know how standard patterns work — don't make them learn new ones.

## Pushback

→ Load [references/pushback.md](references/pushback.md) if not already loaded.

Challenge UX decisions:

- Discoverability issues: features hidden behind non-obvious interactions
- Cognitive load: too much information at once
- Poor progressive disclosure: overwhelming with complexity upfront
- Navigation issues: users can't find their way back
- Platform convention violations: reinventing standard patterns

## Completion

Create `specs/projects/PROJECT_NAME/ui_design.md`:

```markdown
---
status: draft
---

# UI Design: [Project Name]

[Organized sections covering the areas above]
```

For small UI surfaces, this can be folded into `functional_spec.md` instead. Use judgment — if UI design would be <30 lines standalone, fold it in.

Present for review. Iterate if needed. When user confirms, mark `status: complete`.
