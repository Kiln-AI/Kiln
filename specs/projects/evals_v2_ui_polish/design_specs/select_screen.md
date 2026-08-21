# Entry — Select Eval Type (Option A: Recommended-First List)

**Stage:** Step 1 of the Create Eval flow (Evals V2).
**Goal:** Let the user pick an eval type before entering the per-type Create Eval shell. This is a full-width first step.
**Layout direction (Option A):** A single highlighted "recommended" hero row at the top, followed by a vertical list of all remaining eval types.

> Wireframe-level spec. Implement the **structure and content** below. Visual details (exact colors, radii, shadows, type scale) follow the Kiln AI design system — do not invent values.

---

## 1. Page Header

Stacked at the top of the page, left-aligned:

1. **Breadcrumb** — `Specs & Evals · Support Classifier` (the trailing segment is the task name; treat as dynamic).
2. **Title** — `Create Eval` (page H1).
3. **Subtitle** — `Select an eval type. Every type produces the same scores — it just changes how they're computed.`

The header reserves a right-aligned slot for an optional note/annotation element (unused in production; present in the wireframe for design comments).

---

## 2. Eval Type Data

All types share one data shape. Render order is fixed (recommended first):

| # | Name | Description | Tags | Flags |
|---|------|-------------|------|-------|
| 1 | **LLM as Judge** | Grade output against criteria you write — quality, accuracy, rubric pass/fail. | `Uses LLM`, `Graded` | `recommended` |
| 2 | **Code** | Write a custom Python scorer for anything the built-in types can't express. | `Python`, `Beta` | `beta` |
| 3 | **Exact Match** | Output equals an expected value. | `Deterministic` | — |
| 4 | **Pattern Match** | Output matches (or doesn't match) a regular expression. | `Deterministic` | — |
| 5 | **Contains** | Output contains (or doesn't contain) a substring. | `Deterministic` | — |
| 6 | **Set Check** | Compare values from the output against an expected set. | `Deterministic` | — |
| 7 | **Tool Call Check** | Check the agent called the right tools, order, and arguments. | `Agent`, `Reads trace` | — |
| 8 | **Step Count Check** | Count steps in the trace and check they are within bounds. | `Agent`, `Reads trace` | — |

**Tag tone:** the `Beta` tag gets a distinct (beta) tone; all other tags use the default tone.

---

## 3. Recommended Hero Row

A single emphasized row pinned to the top, above the list. Visually heavier than list items (stronger border, soft fill background).

Contents, left → right in one row:
- **Icon** — medium type glyph (placeholder square).
- **Body block:**
  - Row: type **name** (`LLM as Judge`, bold) + a `★ Recommended` chip (recommended tone).
  - **Description** line (full description from table).
  - **Tags row** — render each of the type's tags as chips.
- **Primary action** — `Continue` button, right-aligned.

This row corresponds to item #1 (`LLM as Judge`). It does **not** also appear in the list below.

---

## 4. "All eval types" List

- **Section label:** `All eval types` above the list.
- Vertical stack of rows, one per remaining type (#2–#8, i.e. all types except the recommended one).

Each list row, left → right in one row:
- **Icon** — small type glyph (placeholder square), smaller than the hero icon.
- **Body block:**
  - Row: type **name** (semibold, no wrap) followed inline by its **tag chips**.
  - **Description** line beneath (smaller, dimmer text).
- **Chevron** — right-pointing chevron at the far right indicating the row is clickable/advances.

List rows are lighter weight than the hero: thinner border, plain card background, no per-row primary button (the whole row is the affordance).

---

## 5. Interaction

- Clicking the hero **Continue** button selects `LLM as Judge` and advances to the Create Eval shell (step 2).
- Clicking any **list row** selects that type and advances to the Create Eval shell.
- Selection of a type is the only output of this screen; it determines which per-type form is injected into the shell's left pane downstream.

---

## 6. Notes for the implementer

- The eval-type list is a single source array — the recommended hero and the list are both derived from it (hero = first item, list = the rest). Keep it data-driven, not hardcoded twice.
- This is a full-width step with no Test Run pane (that appears only in step 2, the shell).
- Use the Kiln design system for the page-shell card, typography, chips/badges, buttons, and icon treatment.
