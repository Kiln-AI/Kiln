---
name: data_guides
description: |
  Task Data Guides for synthetic data generation — what they are, the manual vs Kiln Pro authoring flows, the preview/refine loop, and how a guide shapes topic and input generation. Load when: the user mentions a data guide, wants synthetic inputs to match their real data, or is starting SDG on a task with no guide saved.
---
# Knowledge: Data Guides (Synthetic Data)

A **Data Guide** is a single markdown document attached to a task that describes what **realistic inputs** to the task look like — fields and their meaning, formats, lengths, value distributions, presentation conventions. Synthetic data generation reads it so generated inputs match the user's real data instead of the model guessing. It is **input-only by design**: output behavior (schema, classification rules, tone) belongs to the task prompt and output schema, and the guide is deliberately never injected at output generation.

## Knowledge Required

- `references/knowledge/specs_and_evals.md` — when the generated data feeds an eval set. Flag the golden-subset caveat: an SDG-filled test set needs a hand-rated golden subset before its scores are trusted.

## API Docs

Load the relevant endpoint doc **before** making each API call.

| Endpoint | Load |
|----------|------|
| Catalog — Synthetic Data API (guide CRUD + preview/refine) | `references/knowledge/api_docs/synthetic_data_api_list.md` |
| GET the task's guide (`null` + 200 when none) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_data_gen_guide.md` |
| POST save/overwrite the guide | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_data_gen_guide.md` |
| POST preview inputs from a draft guide (not persisted) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_data_gen_guide_preview.md` |
| POST refine the guide via metaprompter (returns markdown — does **not** save) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_data_gen_guide_refine.md` |

These five are the **only** guide endpoints you call. The Kiln Pro draft-job flow is UI-only — never call its endpoints (see below).

## Rigid facts

- **One guide per task.** `POST` creates or overwrites in place — there is no list, no versions. `POST` with a blank body is a **400**; removing a guide is `DELETE` (approval-gated).
- **`source` is `manual` or `kiln_pro`**, and the refine pipeline branches on it (manual = full-guide edits; kiln_pro = surgical feedback-only edits). **Omit `source` on an edit POST** to preserve the existing value — always sending `"manual"` silently flips a Kiln Pro guide onto the wrong refine branch.
- **Where the guide applies:** topic generation (only its `# Semantics` section) and input generation (the whole guide). **Never output generation.** Precedence at generation time: per-call guidance > the Data Guide > model defaults; an eval template's stage guidance also overrides the guide.
- **Guide shapes:** manual guides start as `# Reference Inputs` (`## Example N` blocks — user-owned ground truth, preserved verbatim on refine); refined/Kiln Pro guides use `# Semantics`, `# Style`, `# Presentation Defaults` (Kiln Pro: these three only).

## Two authoring flows

| | Manual | Kiln Pro |
|---|--------|----------|
| Input | A handful of hand-picked example inputs | Up to 200 real examples (past runs, documents, CSV, manual) |
| Rules discovery | Metaprompter derives rules from rated previews + feedback | Cloud job drafts the full guide from the examples |
| Effort / account | ~15 min, no account needed | ~5 min, requires a Kiln Pro account |

Both converge on the same review loop: generate ~5 preview inputs → the user rates each Realistic / Needs Work → feedback → refine → repeat → save.

**The Kiln Pro flow is UI-only — do not drive it via API.** The draft job runs on Kiln's cloud in the background (up to 200 real examples, each ≤200k chars, schema-validated for structured tasks; the user can leave the page and an in-app progress widget tracks it). Route the user to the Kiln Pro setup page (deep links below); the draft lands in the same review-and-refine loop, and only saving persists it.

## API semantics traps

- **Refine never persists.** `data_gen_guide_refine` returns refined markdown; you must `POST` it to save. Preview samples rate as `{input, looks_good}`; for a `kiln_pro` guide only the free-text `feedback` drives changes (ratings are ignored), so feedback should name the specific section or rule to change.
- **`data_guide: null` and `""` differ on the generation endpoints.** On `generate_categories` / `generate_inputs`, `null`/omitted falls back to the task's saved guide; `""` means "explicitly no guide".
- Topic generation always uses the saved guide; the UI's "Use Data Guide" toggle governs input generation only.

## Writing good guide content

- **Measurable over vague.** "Inputs are 5-25 words, 1-3 sentences" beats "inputs are short"; "professional tone" is not a rule. State rules as constraints, not preferences.
- **Quantitative `# Style` constraints act as ceilings** — write the upper bound actually wanted.
- **One fact, one section:** format/length → `# Style`; fields, meaning, cross-field relationships → `# Semantics`; overridable conventions → `# Presentation Defaults`.
- **Don't encode output policy.** Anything about what the *model should produce* belongs in the task prompt, not the guide.
- A pattern seen in one example is a hypothesis; codify what the user confirms via Realistic ratings.

## Agent's role

1. **Recommend a guide before SDG on a task without one** — check with a `GET`; without a guide, generation guesses at input realism.
2. **Default to the UI flows via deep links** — the chooser and review loop are built for rating and iteration. When the user asks you to *just do it*, the API path is sanctioned: draft (or job-draft) → `data_gen_guide_preview` → show samples → refine with their feedback → `POST` (preview/refine/job-start require approval).
3. When generating synthetic data (`generate_categories` / `generate_inputs`), leave `data_guide` unset to inherit the saved guide; pass `""` only when the user explicitly wants generation without it.
4. **Bulk generation belongs in the UI.** For "make me N examples" asks, set up the surface and deep-link the [Synthetic Data page](http://localhost:8757/generate/{project_id}/{task_id}/synth) rather than driving dozens of generate/save calls in chat. If you do save samples via API, load `save_sample`'s api_doc first — its body carries strict source/model metadata that 422s when hand-rolled.

## UI Deep Links

| Action | Link |
|--------|------|
| Synthetic data page (guide intro card appears here) | `http://localhost:8757/generate/{project_id}/{task_id}/synth` |
| Choose authoring flow (Manual vs Kiln Pro) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_chooser` |
| View the saved guide (+ edit / delete) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide` |
| Manual setup (examples + review loop) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_setup` |
| Kiln Pro setup (pick example sources) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_setup_copilot` |

Do **not** deep-link `http://localhost:8757/generate/{project_id}/{task_id}/data_guide/refine` — it requires an in-app handoff and bounces on direct navigation.
