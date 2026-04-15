---
status: complete
---

# UI Design: Task/Project Selector Redesign

## Desktop Layout (>=900px)

```
┌─────────────────────────────────────────────────────────┐
│ Currently selected: Project Name / Task Name            │
├──────────────────┬──────────────────────────────────────┤
│ Projects    [+New] │ Tasks in Project Name        [+New] │
│ Pick a project     │ 14 tasks                           │
│────────────────────│────────────────────────────────────│
│ 📁 Dev Project     │ 📄 Joke Generator                  │
│   Main playground  │    Currently selected              │
│                    │                                    │
│ 📁 Customer Demo   │ 📄 Joke Generator NNN              │
│   Polished tasks   │                                    │
│                    │ 📄 Import Test Joke 2               │
│ 📁 Eval Sandbox    │                                    │
│   Benchmarks...    │ 📄 very structured joke             │
└────────────────────┴────────────────────────────────────┘
```

- Left pane: fixed ~320px width, scrollable list
- Right pane: fills remaining width, scrollable list
- Both panes have rounded borders, subtle background on headers
- Min-height ~500px to give the content room

## Small Screen Layout (<900px)

### State A: Task pane visible (default when project selected)

```
┌─────────────────────────────────┐
│ Currently selected: Proj / Task │
├─────────────────────────────────┤
│ [📁 Dev Project ▼]             │  ← project indicator button
├─────────────────────────────────┤
│ Tasks in Dev Project      [+New]│
│ 14 tasks                        │
│─────────────────────────────────│
│ 📄 Joke Generator               │
│    Currently selected           │
│ 📄 Joke Generator NNN           │
│ 📄 Import Test Joke 2           │
└─────────────────────────────────┘
```

### State B: Project pane visible (after clicking indicator)

```
┌─────────────────────────────────┐
│ Currently selected: Proj / Task │
├─────────────────────────────────┤
│ Projects                  [+New]│
│ Pick a project first            │
│─────────────────────────────────│
│ 📁 Dev Project                  │
│   Main playground               │
│ 📁 Customer Demo                │
│   Polished tasks                │
│ 📁 Eval Sandbox                 │
│   Benchmarks...                 │
└─────────────────────────────────┘
```

Clicking a project selects it and returns to State A.

## Component Styling

Uses DaisyUI + Tailwind classes consistent with the app's existing design system. No custom CSS colors -- rely on `base-200`, `base-300`, `base-content`, `primary`, etc.

### Pane containers
- `bg-base-100` body, `bg-base-200` headers
- `border border-base-300 rounded-2xl`
- Overflow hidden on container, overflow-y-auto on list area

### Row items
- Padding `px-3.5 py-3`, `rounded-xl`
- Hover: `hover:bg-base-200`
- Selected: `bg-primary/10 border border-primary/20`

### Buttons
- "+ New Project" / "+ New Task": `btn btn-sm btn-ghost` or `btn btn-sm btn-outline`
- Standard style, not primary/blue

### Icons
- Folder icon for projects, document icon for tasks
- Small, muted color (`opacity-60`)

### Typography
- Pane titles: `text-sm font-semibold`
- Row names: `text-sm font-medium`
- Row descriptions: `text-xs text-base-content/60`
- "Currently selected" label: `text-xs text-base-content/50`
