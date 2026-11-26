---
name: synthetic_data
description: |
  Synthetic data generation in Kiln: what it makes, why it is done in the app, the strong caution against driving its endpoints from an agent, the rule against making eval data, the workarounds not to use, and the links. Load before any request to generate, add or invent data for a task, an eval or a fine-tune.
---
# Knowledge: Synthetic Data

Kiln's synthetic data generation makes data for a task, for two main goals: the items of an eval (its train, val and test splits), and the training data of a fine-tune. It generates realistic inputs, shaped by the task's Data Guide (`references/knowledge/data_guides.md`), and runs the task on them to make the outputs. The runs are saved to the dataset with tags, for an eval's splits or for a fine-tune. For a RAG task it generates question and answer pairs from the documents.

## The app does this better than an agent

Synthetic data generation is a UI-first case: the app's flow is better than the API driven from a chat. The flow runs in steps, and the user is in each one: they review the plan of what to generate, review the inputs, steer the generation with guidance, and remove bad samples before anything is saved. Each step corrects the one before it. An agent that drives the endpoints skips that review, and the dataset fills with data that nobody checked. That data usually covers fewer cases and is less realistic, and its errors carry into every eval score and fine-tune built on it.

So, by default, send the user to the app:

- **Data for an eval:** the "Add Data for your Eval" page, `http://localhost:8757/dataset/{project_id}/{task_id}/add_data?reason=eval&eval_id={eval_id}` (`references/knowledge/create_eval.md`, "Adding the eval's data"). It sends generated data to the eval's tags.
- **Data for a fine-tune:** the [Create a New Fine Tune](http://localhost:8757/fine_tune/{project_id}/{task_id}/create_finetune) screen. Synthetic data started from there gets the `fine_tune` tag (`references/knowledge/fine_tuning.md`).
- **Other data:** the [Synthetic Data](http://localhost:8757/generate/{project_id}/{task_id}) page.
- **Data Guides:** the flows above ask the user to make a Data Guide when the task needs one (`references/knowledge/data_guides.md`). You need not check for one first.

Say why in one or two sentences, then give the link.

## The rules

1. **Never create eval data.** No eval inputs, no runs made or tagged to fill an eval's splits, no generated inputs or outputs saved for an eval. The user adds an eval's data in the app (`references/knowledge/create_eval.md`).
2. **Other synthetic data: advise strongly against an agent making it.** Recommend the app, and say why. Only when the user has heard why and still asks you to, generate it through the endpoints (below).
3. **Never work around the synthetic data tools.** Making up inputs is synthetic data generation, whichever endpoint carries it. Do not:
   - call `POST .../run` or `POST .../save_sample` many times with inputs you wrote, and then tag the runs for an eval or a fine-tune;
   - create eval inputs;
   - write a CSV of made-up rows for the user to upload;
   - tag existing runs to fill a split, when the user did not name those runs.

   Tagging real runs that the user names is not a workaround (`references/knowledge/create_eval.md`, "Adding the eval's data").

## When the user insists

Only for data that is not eval data, and only after rule 2. Read `references/knowledge/api_docs/synthetic_data_api_list.md`, and each endpoint doc before its call.

- Check for a saved Data Guide first (`references/knowledge/data_guides.md`). Without one, generation guesses at what realistic inputs look like.
- On `generate_categories` and `generate_inputs`, leave `data_guide` unset (or `null`) to use the saved guide. `""` means no guide: pass it only when the user asks for generation without one. Topic generation always uses the saved guide.
- Show the user a small first batch, and change the guidance from their feedback before you generate more. This is the review the app would give them.
- Read the doc of `save_sample` before you save: its body carries source and model metadata that a hand-built body gets wrong (a 422).
- Generation calls models: tell the user the size before a large batch (`references/knowledge/experiment_costing.md`).

## Data in a test set

A test set filled with synthetic data needs a golden subset that the user rates by hand before its scores are trusted (`references/knowledge/specs_and_evals.md`).

## UI Deep Links

| Action | Link |
|--------|------|
| Synthetic data page | `http://localhost:8757/generate/{project_id}/{task_id}` |
| Add data for an eval | `http://localhost:8757/dataset/{project_id}/{task_id}/add_data?reason=eval&eval_id={eval_id}` |
| Add data to the dataset (CSV, synthetic, manual) | `http://localhost:8757/dataset/{project_id}/{task_id}/add_data` |
| Create a fine-tune, with its data | `http://localhost:8757/fine_tune/{project_id}/{task_id}/create_finetune` |
| Choose how to make a Data Guide | `http://localhost:8757/generate/{project_id}/{task_id}/data_guide_chooser` |
