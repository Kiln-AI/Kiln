# Test Run Pane — States

**Context:** The Test Run pane is the **shared right-hand pane** of the Create Eval shell (step 2). It is identical for every eval type — only the left form changes. It lets the user test the scorer against a real dataset input before saving, then walks through its lifecycle: empty → pick input → running → results. A "More options" link opens a full dataset picker modal.

> Wireframe-level spec — implement **structure and content**. Visual details (color, exact type scale) follow the Kiln AI design system. Status indicators are greyscale in the wireframe; semantic color comes in hi-fi.

---

## Shared Pane Frame

Every state (except the modal) renders inside one panel frame:

- Fixed-width vertical pane, full height, ~18px padding, column flex.
- **Header:** `Test Run` title (bold), pinned at top.
- **Body:** flexes to fill.
- **Footer:** optional, separated from the body by a 1px top divider with top padding. Holds the state's primary action(s) and any explanatory note.

### Reused sub-components

- **`SelectedInput`** — labeled `Input`; a single highlighted row showing the chosen dataset item as a mono JSON preview (`{"joke_topic": "cows"}`) with a relative timestamp (`2h ago`), and a right-aligned **Change** affordance. `Change` is **enabled in results**, **locked (disabled/dimmed) while running**.
- **`DatasetRow`** — selectable recent-input row: radio + mono input preview (truncated) + relative time. Selected state gets a stronger border and fill. No model shown.
- **`MoreOptions`** — underlined `More options` link + dim caption `— browse all dataset inputs`. Opens the input-picker modal (State 5).
- **`StatusDot`** — greyscale status glyph: `pass` ✓ (filled), `fail` ✕ (outlined), `skip` – (dashed outline).

---

## State 1 — Empty Dataset

The task has no dataset inputs yet, so there is nothing to test against.

- **Body:** `Input` section label, then a large dashed-border placeholder card, centered:
  - Icon glyph
  - Title: `No sample inputs yet`
  - Body: `Run your task to generate inputs in the dataset, then test against them here.`
  - Secondary button: `Go to Run`
- **Footer:** full-width outline button `Save Without Testing` (the only forward path here). It triggers the "Save without testing?" confirm modal.

---

## State 2 — Input Picker (Ready)

Dataset inputs exist; user picks one and runs.

- **Body:**
  - Section label: `Input · recent dataset items`
  - Stack of 4 `DatasetRow`s (first selected by default). Sample data:
    - `{"joke_topic": "cows"}` · 2h ago *(selected)*
    - `{"joke_topic": "kubernetes"}` · yesterday
    - `{"joke_topic": "startup valuations"}` · yesterday
    - `{"joke_topic": "cows and dogs"}` · 3d ago
  - `More options` link beneath the list → opens the input-picker modal.
  - Full-width **primary `Run`** button.
  - Note: the first Run (or Save) in a session opens the "Trust this code?" gate (code evals only).
- **Footer:** `Results` section label over a dashed placeholder box reading `Run to see scores`.

---

## State 3 — Running

The scorer is executing.

- **Body top:** `SelectedInput` with **Change locked** (`changeable={false}`).
- **Center, stacked & centered:**
  - Spinner
  - Title: `Running…`
  - Caption: `Executing the scorer on your input`
  - Outline **`Cancel`** button (always available — runs can be long, esp. code & LLM judge).
- No footer.

---

## State 4 — Results (pass / fail / skipped)

The test completed; show per-score results as a preview (not yet saved).

- **Body top:** `SelectedInput` with **Change enabled**.
- **Scores header row:** `Scores` label on the left, italic `preview · not saved` on the right.
- **Score rows** — each: `StatusDot` + score **name** (bold) + score **type** (dim sub-label) + right-aligned **value**. Skipped rows show their value in dim text. Sample data:
  - `Helpfulness` — `five_star (1–5)` — `4 / 5` — **pass**
  - `Faithfulness` — `pass_fail` — `Pass` — **pass**
  - `Tone match` — `pass_fail · needs reference` — `Skipped` — **skip**
- **Inline annotation** below the rows (italic, soft callout): `"Tone match" skipped: no reference data on this item — skips are excluded from averages, shown via tooltip.`
- **Footer:**
  - Legend row: `Used` (pass), `Skipped` (skip), `Fail` glyphs with labels.
  - Actions: `Run again` (default button) + full-width primary **`Save Eval`**.
  - Note: a successful test enables Save. Server validates that all declared scores are returned — **missing = warning, wrong type = error**.

---

## State 5 — Input Picker Modal ("More options")

Opened from the `More options` link. A centered dialog (~620px wide) over a backdrop, for browsing/selecting any dataset input — wider and more detailed than the inline list.

- **Header:** title `Choose an input` + subtitle `Pick a dataset item to test this scorer against.` + a close (✕) button top-right.
- **Search field:** full-width input with search icon, placeholder `Search inputs…`.
- **Table:**
  - Column headers (uppercase, dim): `Input preview` · `Tags` · `Created`.
  - Rows: radio + mono input preview (truncated) + a tag chip (or `None`) + relative created time. First row selected. Sample data:
    - `{"joke_topic": "cows"}` · `manual_run` · 2h ago *(selected)*
    - `{"joke_topic": "kubernetes"}` · `synthetic_batch_1` · yesterday
    - `{"joke_topic": "startup valuations"}` · `eval_candidate` · yesterday
    - `{"joke_topic": "cows and dogs"}` · `manual_run` · 3d ago
    - `{"joke_topic": "why does the cow"}` · None · 5d ago
- **Footer:** left = result count caption (`248 inputs · showing 5`); right = `Cancel` (default) + `Use input` (primary).

---

## State Transitions

```
Empty ──(Save Without Testing)──▶ "Save without testing?" modal
Picker ──(Run)──▶ [Trust gate, 1st time, code only] ──▶ Running ──▶ Results
Picker ──(More options)──▶ Input Picker Modal ──(Use input)──▶ Picker (new input selected)
Running ──(Cancel)──▶ Picker
Results ──(Run again)──▶ Running
Results ──(Change)──▶ Picker / Input Picker Modal
Results ──(Save Eval)──▶ eval saved
```

## Implementer notes

- All states share the same pane frame and width — only body/footer content swaps.
- The pane is **type-agnostic**: never reference the selected eval type's specific form here.
- Status indicators are greyscale placeholders in the wireframe; map to semantic colors (success / neutral-skip / error) in hi-fi per the Kiln palette.
