---
status: complete
---

# Evals V2 — Builder UI Remediation (bridge current → spec)

## What this is

The Evals V2 project (`/specs/projects/evals_v2/`) specced a rich UX for the eval-building
UI. The coding agent that implemented Phase 6 made a major fumble: it went off-book and
built its own UI rather than the one that was specced. The bones are there, but it is not
remotely to spec.

This is **not** a re-spec. The screens are already well defined in the Evals V2 spec —
chiefly `components/70_builder_and_onboarding.md` (and its companions `components/27`
code-eval and `components/22` deterministic types). Those reviewed specs are the
**destination**. This project's job is the **bridge from what we have to what we specced**.

## Why it happened (so we scope the fix correctly)

The speccing work made it into the spec, but was lost at the phase-6 *plan* decomposition
step — the coding agent then faithfully built the degraded plan. This is a fidelity loss at
decomposition, not a missing spec and not (only) a rogue coder. **The implementation plan is
not the entire spec.** Because of that, I no longer trust the phase-6 build at all and want a
**full review** of what was missed — not just the items I already happen to know about.

## The work

1. **Full review (done as the first step):** a from-scratch audit of the built Phase-6 UI
   against `components/70` (+ `27`, `22`), with file:line evidence — because I don't trust
   any prior "it followed the spec" claim. (Findings captured in this project's functional
   spec.)
2. **A functional spec that bridges current → spec:** for each area, *current state →
   target (pointing at the real reviewed spec section) → the delta to close*. It points to
   the existing specs as the destination; it does **not** restate or re-spec the screens.
3. **An architecture plan for the conversion:** how we get from what we have to what we
   specced — sequencing, what to keep vs. replace, and the cross-cutting UI-architecture fix
   below.

## Cross-cutting UI-architecture concern (must be addressed)

The coding agent built a faulty navigation architecture for the builder UI:

- It put an **on-screen Back button** inside the page and a **hand-rolled in-page state
  machine** (many separate components sharing a single Svelte page, switched by a local
  variable) to move between picker → form → test.
- I want a **real native back stack**. When we do "navigation within a page" it should use
  the **proper SvelteKit history API** (URL/route/history) so the browser Back button works
  naturally — **not** a new in-page back stack or an on-screen back button.

Note: `components/70 §1` already mandated "push history / update URL the SvelteKit-official
way, so Back returns to the picker." The build ignored it. So this is partly enforcing the
existing spec and partly a broader architecture principle for the conversion.

## Guardrails

- **Point to the real specs as the destination — do not re-spec the screens.** The detail
  lives in `components/70` (+ `21`, `27`, `22`); cite sections, don't duplicate them.
- Preserve the parts that already match spec (CodeMirror editor, lazy-load, trust gate,
  per-type forms' existence) rather than rewriting wholesale.

## Scope refinement (post-review)

After the full review + a cross-check against a second agent's findings
(`alt_agent_project_overview.md`, retained as a reference input), the project was refined:

- **Scoped to the MANUAL create flow only.** Copilot / eval-builder / questionnaire, the
  view / run-result surfaces, and read-only-config-detail + clone/prefill are **separate
  projects** (see `functional_spec §5`).
- **New ship-blocker found:** the manual `llm_judge` create path still emits **V1**, not V2.
  Fixing it (backend-baked V2 `llm_judge` from `output_scores`) is now a core phase — my
  original review missed this; the second agent caught it.
- **Mostly frontend, plus a focused backend addition** for the V2 `llm_judge` baking (a
  canonical Python template + score-scale helper shared with `build_score_schema`).
- **Score rendering keeps V1 parity** (float printing); no typed score-badge.

Decisions are recorded in `functional_spec §6`; the conversion plan is in `architecture.md`.
