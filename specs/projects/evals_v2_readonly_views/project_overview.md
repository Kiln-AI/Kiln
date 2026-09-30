---
status: NOT PLANNED (folded into scosman/evals_v2_ui_fix — scosman, 2026-06-26)
ship_gating: ship-blocker (sequenced — blocked on Project 1)
depends_on: scosman/evals_v2_ui_fix  (project specs/projects/eval_create_ui_v2 — must complete first)
---

# Project: Evals V2 read-only config views

## ⛔ NOT PLANNED — superseded

**This standalone project is not being built.** The underlying gap (the read-only config-detail
view — i.e. the `"No description provided."` regression for non-`llm_judge` V2 types in the
"Eval Instructions" column on the Compare Judges page) is being addressed directly in the
**`scosman/evals_v2_ui_fix`** branch (Manual eval create UI V2), not here.

**Why the change:** §4.3 offers two mechanisms — *reuse the per-type `createForm` in readonly mode*,
**or** *a lightweight per-type `configDetail` renderer*. This project assumed the first, which is
why it was sequenced **after** Project 1 (it needed Project 1's rebuilt forms). Choosing the second —
a small per-type `eval_config_to_description()` rendered in the **existing** "Eval Instructions"
column + "See all" modal (`eval_config_instruction.svelte`) — restores **V1 parity** with:

- **no new route** (§4.2 explicitly forbids new routes — V2 renders where V1 already does; the
  earlier "add an `[eval_config_id]` detail route" framing in this doc was wrong),
- **no readonly-form mode**, and therefore
- **no dependency on Project 1** — so it no longer needs its own sequenced project; it's a small,
  parallel-safe fix that fits inside the UI-fix branch.

What's given up vs. this project is only the *richer* §4.1 rendering (read-only CodeMirror for
`code_eval`, structured field layout, Beta badge, "Advanced" collapse) — all **above** V1 parity,
not parity itself. **Clone / prefill-from-existing** remains deferred for V2.0 (unchanged).

The original plan is preserved below for reference.

---

## Summary

Build a **read-only config-detail view** for V2 eval configs so a user can inspect what a saved candidate config actually does — its type and key properties (the judge rubric/model, the code, the regex, the expected values, the tool-call matchers, etc.) — **before cloning it**. EvalConfigs are immutable/clone-only, so being able to see a config read-only is a `components/70 §4.3` V2.0 requirement. Today this is missing for non-`llm_judge` V2 types.

## ⚠ Hard dependency — do not start until Project 1 is done

This project **reuses the per-type create-form components in a disabled/read-only mode** (per `components/70 §4.3`: *"reuses the same per-type module's `createForm` in a disabled/read-only mode, or a lightweight `configDetail` renderer"*). Those form components are being **rebuilt** by the **Manual eval create UI (V2)** project on branch **`scosman/evals_v2_ui_fix`** (`specs/projects/eval_create_ui_v2/project_overview.md`).

**Start only after that work lands** — the "final edit views" (the rebuilt per-type forms) must be finalized first; otherwise this project would build read-only views against forms that are about to be rewritten. Fork this project's branch from the completed `scosman/evals_v2_ui_fix` work.

## Source specs (committed)

- `specs/projects/evals_v2/components/70_builder_and_onboarding.md` — **§4.3** (read-only config-detail view in scope for V2.0; reuse per-type form in readonly mode or a `configDetail` renderer), **§4.1** (per-type config-detail content — the right-hand "Read-only config-detail shows" column: criteria/rubric/model for `llm_judge`; read-only code for `code_eval`; value expression + comparison source + case-sensitivity for the deterministic types; etc.), **§1 / E.17** (clone-not-edit context — why a read-only view is needed).
- Triage source of truth: `specs/projects/evals_v2/spec_fidelity_review/DECISIONS.md` (decision **D32**).
- Evidence: `specs/projects/evals_v2/spec_fidelity_review/unit_70b-view-surfaces.md`, `.../confirm_H.md`.

## Scope (decision D32)

- A read-only view of any saved V2 EvalConfig showing its type + key properties (content = the per-type "config-detail" column in `§4.1`).
- A **"View" affordance** to reach it from the eval-detail page and the eval-configs list.
- Mechanism (implementer's choice per §4.3): render the per-type module's `createForm` in a `disabled`/`readonly` mode, **or** a lightweight per-type `configDetail` renderer.

### Current state (what's wrong today)
- `app/web_ui/src/lib/components/.../eval_config_instruction.svelte` reads only `task_description`/`eval_steps`, so a non-`llm_judge` V2 config renders **"No description provided"** in the eval-configs comparison/list surface.
- There is no `[eval_config_id]` detail route, and the per-type forms have no readonly/disabled mode (this project adds it — on top of Project 1's rebuilt forms).

## Out of scope

- **Clone / prefill-from-existing** — **deferred** for V2.0 (scosman, 2026-06-24). It shares mechanics with this project (the readonly/initial-value form props this project adds are most of what clone needs), so if it's ever un-deferred it would extend this project — but it is **not** in scope now.
- The other view-surface fixes (Thinking-column reasoning, `n_excluded` warning) live in the cleanup project (`specs/projects/evals_v2_cleanup/`), not here.

## Acceptance criteria

- A user can open any saved V2 EvalConfig (all 8 types) from the eval-detail page or the configs list and see its key properties **read-only** — no more "No description provided" for non-`llm_judge` types.
- Built on the finalized per-type forms from `scosman/evals_v2_ui_fix` (no fork of form logic).
- All checks pass (`npm run check`/`lint`/`test_run`/`build`; backend unaffected).
