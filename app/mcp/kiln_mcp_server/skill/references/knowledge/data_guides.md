---
name: data_guides
description: |
  Task Data Guides for synthetic data generation — what they are, why the user makes one in the app, the manual and Kiln Pro ways to make one, the preview/refine loop, and how a guide shapes topic and input generation. Load when: the user mentions a data guide, wants synthetic inputs to match their real data, or is starting SDG on a task with no guide saved.
---
# Knowledge: Data Guides (Synthetic Data)

A **Data Guide** is a single markdown document attached to a task that describes what **realistic inputs** to the task look like — fields and their meaning, formats, lengths, value distributions, presentation conventions. Synthetic data generation reads it so generated inputs match the user's real data instead of the model guessing. It is **input-only by design**: output behavior (schema, classification rules, tone) belongs to the task prompt and output schema, and the guide is deliberately never injected at output generation.

## Knowledge Required

- `references/knowledge/synthetic_data.md` — the generation that a guide shapes, and why it is done in the app

## API Docs

Load the relevant endpoint doc **before** making each API call.

| Endpoint | Load |
|----------|------|
| Catalog — Synthetic Data API (guide CRUD + preview/refine) | `references/knowledge/api_docs/synthetic_data_api_list.md` |
| GET the task's guide (`null` + 200 when none) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_data_gen_guide.md` |
| POST save/overwrite the guide | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_data_gen_guide.md` |
| POST preview inputs from a draft guide (not persisted) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_data_gen_guide_preview.md` |
| POST refine the guide via metaprompter (returns markdown — does **not** save) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_data_gen_guide_refine.md` |

These five are the guide endpoints: read a guide, and change one when the user asks (below). The Kiln Pro draft job has its own endpoints in the same catalog; it runs in the app.

## Rigid facts

- **One guide per task.** `POST` creates or overwrites in place — there is no list, no versions. `POST` with a blank body is a **400**; removing a guide is `DELETE` (ask the user first).
- **`source` is `manual` or `kiln_pro`**, and the refine pipeline branches on it (manual = full-guide edits; kiln_pro = surgical feedback-only edits). **Omit `source` on an edit POST** to preserve the existing value — always sending `"manual"` silently flips a Kiln Pro guide onto the wrong refine branch.
- **Where the guide applies:** topic generation (only its `# Semantics` section) and input generation (the whole guide). **Never output generation.** Precedence at generation time: per-call guidance > the Data Guide > model defaults; an eval template's stage guidance also overrides the guide.
- **Guide shapes:** manual guides start as `# Reference Inputs` (`## Example N` blocks — user-owned ground truth, preserved verbatim on refine); refined/Kiln Pro guides use `# Semantics`, `# Style`, `# Presentation Defaults` (Kiln Pro: these three only).

## Making a guide is done in the app

Making a Data Guide is a UI-first case: the app's flow is better than the API driven from a chat. Send the user to the [Data Guide chooser](http://localhost:8757/generate/{project_id}/{task_id}/data_guide_chooser), and say why: the app lets them pick real samples to learn from, upload a dataset, and rate preview inputs in a feedback loop that refines the guide. A guide written in a chat misses the user's real examples and their ratings, and every input generated later inherits its mistakes.

The chooser offers two ways:

| | Kiln Pro | Manual |
|---|--------|----------|
| How | The user uploads or picks real examples. Kiln's server reads them and builds the guide | The user adds a handful of example inputs. Kiln derives rules from their ratings of preview inputs and their feedback |
| Examples | Up to 200 real examples (past runs, documents, CSV, typed in) | A handful, picked by hand |
| Effort / account | ~5 min, requires a Kiln Pro account | ~15 min, no account needed |

**Kiln Pro is the most powerful way**: the server builds the guide from many real examples, so recommend it first. When the user has no Kiln Pro account, recommend signing in at [Kiln Pro](http://localhost:8757/settings/providers/kiln_pro), or the manual way.

Both ways end in the same review loop: ~5 preview inputs → the user rates each Realistic / Needs Work → feedback → refine → repeat → save. The Kiln Pro draft runs on Kiln's cloud in the background; the user can leave the page, and an in-app progress widget tracks it. Only saving persists the guide.

## API semantics traps

- **Refine never persists.** `data_gen_guide_refine` returns refined markdown; you must `POST` it to save. Preview samples rate as `{input, looks_good}`; for a `kiln_pro` guide only the free-text `feedback` drives changes (ratings are ignored), so feedback should name the specific section or rule to change.
- Topic generation always uses the saved guide; the UI's "Use Data Guide" toggle governs input generation only.

## Writing good guide content

- **Measurable over vague.** "Inputs are 5-25 words, 1-3 sentences" beats "inputs are short"; "professional tone" is not a rule. State rules as constraints, not preferences.
- **Quantitative `# Style` constraints act as ceilings** — write the upper bound actually wanted.
- **One fact, one section:** format/length → `# Style`; fields, meaning, cross-field relationships → `# Semantics`; overridable conventions → `# Presentation Defaults`.
- **Don't encode output policy.** Anything about what the *model should produce* belongs in the task prompt, not the guide.
- A pattern seen in one example is a hypothesis; codify what the user confirms via Realistic ratings.

## Agent's role

1. **Recommend a guide before synthetic data generation on a task without one.** Check with a `GET`; without a guide, generation guesses at what realistic inputs look like.
2. **Send the user to the chooser to make one** (above).
3. **Read, explain and edit a saved guide.** Read it with a `GET`. When the user asks for a specific change, draft it, preview it with `data_gen_guide_preview`, show the samples, and `POST` it after they agree. Preview and refine call models: say so before you start them.
4. When the user asks you to write a whole guide in the chat after hearing why the app is better, use the same draft → preview → feedback → refine → `POST` loop, with the user rating each preview.

## UI Deep Links

| Action | Link |
|--------|------|
| Synthetic data page (guide intro card appears here) | `http://localhost:8757/generate/{project_id}/{task_id}/synth` |
| Choose how to make a guide (Kiln Pro or manual) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_chooser` |
| View the saved guide (+ edit / delete) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide` |
| Manual setup (examples + review loop) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_setup` |
| Kiln Pro setup (pick example sources) | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_setup_copilot` |

Do **not** deep-link `http://localhost:8757/generate/{project_id}/{task_id}/data_guide/refine` — it requires an in-app handoff and bounces on direct navigation.
