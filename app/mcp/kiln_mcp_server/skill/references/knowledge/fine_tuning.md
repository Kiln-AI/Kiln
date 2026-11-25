---
name: fine_tuning
description: |
  Knowledge for fine-tuning a model on task data — workflow, when to use fine-tuning vs. alternatives, dataset requirements, three archetypes (standard / reasoning / tool-use), provider breakdown, pre-submission confirmation rule, cost guidance from the docs, status checking. Loaded by Improve Task when the user mentions fine-tuning or training a custom model.
---
# Knowledge: Fine-Tuning

One-file home for fine-tuning questions: **when to fine-tune** (vs. prompt engineering, model upgrade, RAG), **how to run a job**, **the three archetypes** (standard, reasoning, tool-use), **dataset/tag requirements**, and **status checking**. When the next step is comparing the fine-tuned model with existing configs, follow, in a chat with a user, `references/client_guidance/chat/running_an_experiment_from_chat.md` ("Variants").

## Knowledge Required

The Kiln docs have three end-to-end guides — load the relevant one when the user's intent matches:

- `references/docs/fine-tuning/fine-tuning-guide.md` — standard fine-tuning end-to-end (synthetic data → dispatch → deploy → evaluate). The canonical reference for the full workflow. Includes a real cost breakdown (see Cost Guidance below).
- `references/docs/fine-tuning/guide-train-a-reasoning-model.md` — distill a reasoning model (R1-style). Use when the user's task benefits from reasoning / "thinking" outputs.
- `references/docs/fine-tuning/fine-tuning-for-tool-use.md` — fine-tune for tool calling. Use when the user's task is tool/agent-shaped and they want a smaller model to reliably call a fixed tool set.

In a chat with a user, also read `references/client_guidance/chat/improve_task.md` when the user is weighing fine-tuning against prompt-level fixes.

## Try First (before fine-tuning)

What to try before a fine-tune, and in what order, is the knowledge's: read `references/improving_agents/playbooks/ordering-work.md` before you recommend one. The training charge is paid as soon as the job is submitted (and cancelling mid-run still typically bills partial cost), so the bar for committing to a training run should be high.

Start a fine-tune only with the user's sign-off, after you explain its downsides and the other options are exhausted. The downsides: a fine-tuned model is much harder to host and scale; it is harder to move to a new model (the fine-tune must be done again); its experiments are expensive and slow; and it can overfit (better on the evals, worse in other areas). It is mostly for expert users.

## When Fine-Tuning Is the Right Lever

Fine-tuning is warranted when:
- The task has a **large, high-quality labeled dataset** — the [Ladder data strategy](references/docs/fine-tuning/fine-tuning-guide.md#our-ladder-data-strategy) target is ~1000 synthetic samples on top of ~10 manual + ~30 LLM-generated. Below ~50 samples, prompt engineering almost always wins.
- You need **style or format consistency** that even a strong prompt cannot lock in.
- **Inference latency or cost is a constraint** — a smaller fine-tuned model can match a larger base model. Per the docs' demo, Llama 3.2 1b after fine-tuning was ~10× faster and ~150× cheaper than the model used for synthetic data gen.
- **Tool-calling reliability** — fine-tuning teaches a smaller model when to call which tool with what parameters; cuts error rates dramatically (see Tool-Use archetype).
- **Reasoning distillation** — distill a reasoning model's behavior into a smaller, faster model (see Reasoning archetype).

## The Three Archetypes

### 1. Standard Fine-Tune

Train on `(input → final output)` pairs. The most common archetype. Use `data_strategy: final_only`. Workflow is the standard 7-step path below.

### 2. Reasoning Fine-Tune

Distill a reasoning model's behavior into a smaller model. Workflow follows the standard path with three modifications (per `references/docs/fine-tuning/guide-train-a-reasoning-model.md`):

- Training data must include reasoning data — the user generates it with a reasoning model in the app's synthetic data flow (`references/knowledge/synthetic_data.md`).
- When creating the dataset, **filter to reasoning samples only** ("Filter to Reasoning Samples" toggle in the UI).
- Choose `data_strategy: final_and_intermediate` (UI: "Thinking — Learn both thinking and final response"). `final_only` will produce a viable model but won't learn reasoning.

When calling the fine-tuned model, always use the same prompt the model was trained with — model performance degrades on prompts it didn't see at training time.

### 3. Tool-Use Fine-Tune

Train a smaller model to call a fixed set of tools reliably (see `references/docs/fine-tuning/fine-tuning-for-tool-use.md`). Strict requirement: **the tool set during training data generation must exactly match the tool set the fine-tune targets.** Kiln rejects training samples whose toolset doesn't match — otherwise the model would learn (incorrectly) to skip a tool that should have been called.

Distillation pattern: large model + long prompt → generate training data → fine-tune small model + short prompt → small model reproduces tool-calling quality at lower cost. After deploying, **always provide the same tools** as during training; adding/removing tools triggers a warning because performance is unlikely to hold.

Use Kiln's [tool-use eval](references/docs/evals-and-specs/evaluate-appropriate-tool-use.md) to verify the fine-tune is actually improving over the base model.

## Cost Guidance

**Specific per-token training costs and live fine-tuned inference costs are not available through Kiln's APIs, the model info endpoints included.** Never invent dollar figures or per-token training pricing — those are provider-specific and change frequently. Direct the user to the provider's current pricing page.

### Authoritative cost examples (from the Kiln docs' demo project)

These come from `references/docs/fine-tuning/fine-tuning-guide.md` and reflect a real ~920-sample dataset; they are illustrative, not a quote for the user's specific job:

| Job | Provider | Cost (USD) |
|-----|----------|-----------|
| 5× Llama models + Mixtral | Fireworks | $1.47 |
| Fine-tune GPT-4o Mini | OpenAI | $2.03 |
| Fine-tune GPT-4o | OpenAI | $16.91 |
| Llama 3.2 (1b & 3b) | Unsloth on Colab T4 | $0.00 |
| Training data generation (920 samples) | OpenRouter | $2.06 |

You may quote these specific numbers (with the "demo dataset, your job will differ" caveat) when the user asks for ballpark cost guidance — they are documented examples, not speculation.

### Qualitative provider cost ordering

When the user is choosing between providers and wants relative cost guidance, this ordering holds (corroborated by the table above):

- **Economical:** **Fireworks**, **Together AI** — open-weight bases are generally the most cost-effective option for fine-tuning.
- **Mid-range:** OpenAI's smaller / mini-tier base models — workable cost for staying on a proprietary stack.
- **Expensive:** OpenAI's larger base models and **Vertex (Gemini)** — large proprietary bases can be prohibitively expensive for both training and inference.

Do not name specific base-model versions in this guidance — model names rot fast. For the current roster and pricing, call `GET /api/finetune_providers`.

Filter recommendations to providers the user has connected (`agent_overview.connected_providers`).

## Provider + Base-Model Breakdown

Per the docs and the `GET /api/finetune_providers` endpoint, the providers Kiln supports for fine-tuning:

- **OpenAI** — proprietary GPT base models across mini and larger tiers. Auto-deployed serverless after training.
- **Fireworks AI** — wide open-weight catalog spanning multiple families and sizes (loaded live from Fireworks). Auto-deployed serverless; new models appear automatically as Fireworks releases them.
- **Together AI** — open-weight base models across multiple families and sizes. Auto-deployed serverless.
- **Vertex AI (Google Gemini)** — Google Gemini base models. **Not auto-deployed.** Kiln generates the training format; the user runs the job themselves following Google's Vertex tune documentation, then uses the resulting model.
- **Self-hosted (Unsloth / Axolotl)** — export the dataset as JSONL and tune locally / on Colab. Not deployed by Kiln; the user runs the model themselves (Ollama is one path).

**Never quote specific base-model versions from this file** — model rosters change frequently and version names date quickly. Always call `GET /api/finetune_providers` to surface the live list of currently-supported base models per connected provider.

## Tag Requirement

**All training data must be tagged with `fine_tune` (or any tag starting with `fine_tune_`, e.g. `fine_tune_thinking`, `fine_tune_experiment_42`).** Kiln will not include un-tagged samples in a fine-tune dataset.

If the user launches synthetic data gen from within the "Create a New Fine Tune" screen, the `fine_tune` tag is added automatically. For pre-existing data, the user adds the tag via the Dataset tab.

When the agent is helping a user prep for a fine-tune and `finetune_dataset_info` shows zero eligible samples, the cause is almost always missing `fine_tune*` tags — call this out specifically rather than just saying "no eligible data."

## Pre-Submission Confirmation Rule

**Submitting `POST /finetunes` starts a billable training run that costs real money the moment it lands** — the training charge is not refundable, and cancelling mid-run typically still bills partial cost. The output model + Kiln `Finetune` record can be deleted later, but the spent training cost cannot be recovered. Before calling `POST /api/projects/{project_id}/tasks/{task_id}/finetunes`, always:

1. Fetch the available providers and base models (`GET /api/finetune_providers`).
2. Fetch the applicable hyperparameters (`GET /api/finetune/hyperparameters/{provider_id}`).
3. Fetch the available dataset splits (`GET /api/projects/{project_id}/tasks/{task_id}/dataset_splits`) and surface `split_contents` counts so the user can verify the right split.
4. **Show the user the full POST body** — all required fields resolved: `provider`, `base_model_id`, `dataset_id`, `train_split_name`, `data_strategy`, and every hyperparameter value (including any non-default values). Flag unusual choices (e.g., `batch_size: 2` is lower than typical defaults).
5. **Wait for explicit user confirmation** before submitting. This is one of the narrow cases where the "Default to executing" rule does NOT apply — a fine-tune job submission is not cheap or reversible.

## Prepare the Config, Let the User Submit (preferred pattern)

`POST /api/projects/{project_id}/tasks/{task_id}/finetunes` is a single call that **creates and submits** the fine-tune job — there is no draft/dry-run mode. The safest pattern is for the agent to do everything UP TO the final POST, then hand off to the user:

1. Prepare the dataset split (`POST /dataset_splits` is cheap and reversible — fine to do directly).
2. Resolve provider, base model, hyperparameters, data strategy, and a sanitized name.
3. Show the full resolved configuration (per the Confirmation Rule above).
4. **Hand the user a UI deep-link** for the fine-tune setup page so they can review and click "Start" themselves.

Avoid POSTing the finetune from chat unless the user explicitly asks ("go ahead and start it" — and even then, follow the confirmation rule).

## Grid Search (multiple variants)

When the user wants to try several fine-tune variants (different base models, different `n_epochs`, different `learning_rate_multiplier`):

1. Confirm the dataset and split with the user (one shared dataset across all jobs).
2. List the variants in a table — one row per intended job, columns for `provider`, `base_model_id`, varying parameters, and constants.
3. Apply Prepare-the-Config / Let-the-User-Submit. Hand the user the deep-link and tell them which variants to launch. Do not POST a batch from chat unless the user explicitly asks for it — multiple training runs is multiple training charges.
4. After the jobs run, compare the resulting fine-tuned models (`kiln_fine_tune` provider run configs, one per resulting model), in a chat with a user as `references/client_guidance/chat/running_an_experiment_from_chat.md` ("Variants") says; `references/knowledge/eval_scores.md` reads the scores.

A grid of more than ~4 jobs is rarely the right answer — costs multiply linearly. Lead with 2–3 well-chosen variants and add more only if the first batch is inconclusive.

## Workflow (API steps)

### Step 1 — Assess readiness

`GET /api/projects/{project_id}/tasks/{task_id}/finetune_dataset_info` returns:
- `finetune_tags` — counts by tag, including high-quality count and reasoning-data count.
- `existing_datasets` — already-frozen splits.
- `existing_finetunes` — prior jobs (for reference / status checks).

Surface counts before any further step. If `eligible_datasets` / `finetune_tags` are empty, the user almost certainly has missing `fine_tune*` tags (see Tag Requirement).

### Step 2 — Create a dataset split (if needed)

`POST /api/projects/{project_id}/tasks/{task_id}/dataset_splits`. Typical 80/20 or 90/10 train/validation. Validation split is optional but recommended.

### Step 3 — Choose provider and base model

`GET /api/finetune_providers` for the live list. Confirm the provider is `enabled: true`.

### Step 4 — Fetch hyperparameters

`GET /api/finetune/hyperparameters/{provider_id}` for provider-specific parameters (`n_epochs`, `batch_size`, `learning_rate_multiplier`, etc.) with types, descriptions, and optional flags.

### Step 5 — Preview and confirm (per the Confirmation Rule)

### Step 6 — Submit (or hand off to UI per Prepare-Config pattern)

`POST /api/projects/{project_id}/tasks/{task_id}/finetunes`.

### Step 7 — Monitor status

Fine-tuning is **not** a background job — there is no `/api/jobs` watcher and no `finetune` job type. Monitor via the fine-tune status endpoint:

- **Status read:** `GET /api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}` — `status.status` is one of `unknown` / `pending` / `running` / `completed` / `failed`. On failure, surface `status.message` and `status.error_details`. There's nothing to wait/block on locally (training runs remotely on the provider); check status when the user asks rather than busy-looping. See `references/knowledge/api_docs/finetuning_api_list.md`.

## After Fine-Tuning Completes

When `latest_status = completed`, `fine_tune_model_id` contains the provider's model ID. For OpenAI / Fireworks / Together, the model is **auto-deployed serverless** — only pay for usage tokens, no recurring deployment cost. Vertex Gemini and self-hosted require manual deployment.

To use the model in Kiln:
1. Create a run config with `model_provider_name: kiln_fine_tune` and `model_name: {fine_tune_model_id}`.
2. Compare it with the existing base-model configs, in a chat with a user as `references/client_guidance/chat/running_an_experiment_from_chat.md` ("Variants") says; `references/knowledge/eval_scores.md` reads the scores.

### Iteration loop (recurring patterns)

Per the docs:
- **Bug → repair → re-train.** Use Kiln's [repair UI](references/docs/repairing-responses.md) for one-off bugs; the corrections feed the next training run.
- **Recurring failure mode → synthetic data with human guidance → re-train.** The user generates samples covering the failure class in the app's synthetic data flow (`references/knowledge/synthetic_data.md`).
- **Rate the dataset; train only on highly-rated content** — reduces noise.
- **Try shorter training prompts** to reduce inference cost — train with the prompt you intend to deploy with.

## Status / Deployment Gotchas

- **Fireworks "Model not found, inaccessible, and/or not deployed"** — Fireworks un-deploys idle fine-tuned models. Opening the model in the "Fine Tune" tab triggers a re-deploy. If a user reports this error, point them at the Fine Tune tab.
- **Train-time prompt vs. runtime prompt mismatch** — fine-tuned models perform best when called with the same prompt used at training. If quality is unexpectedly low, ask whether the runtime prompt matches the train-time prompt (visible in the "Fine Tune" tab).
- **Tool-use fine-tune with mismatched tool set** — if a user reports degraded tool-calling, check whether the runtime tool set matches the training tool set.

## Tracking + Metrics

Per `references/docs/fine-tuning/fine-tuning-guide.md`: Kiln supports **Weights & Biases tracking** for Fireworks and Together jobs. Configure the W&B API key in `Settings > AI Providers & Models > Weights & Biases` before starting the job. OpenAI doesn't support W&B, but provides similar metrics in OpenAI's dashboard (linked from Kiln's Fine Tune page).

For deterministic tasks (e.g., classification), Kiln passes the validation set to OpenAI / Together at train time and the provider reports `val_loss`. For non-deterministic tasks, use Kiln's eval tools after training.

## API Docs

Load the relevant endpoint doc **before** each API call.

| Endpoint | Load |
|----------|------|
| Fine-tuning — catalog | `references/knowledge/api_docs/finetuning_api_list.md` |
| GET finetune dataset info | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_finetune_dataset_info.md` |
| GET dataset splits | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_dataset_splits.md` |
| POST create dataset split | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_dataset_splits.md` |
| GET finetune providers | `references/knowledge/api_docs/get_api_finetune_providers.md` |
| GET finetune hyperparameters | `references/knowledge/api_docs/get_api_finetune_hyperparameters_provider_id.md` |
| POST create finetune | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_finetunes.md` |
| GET finetune status | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_finetunes_finetune_id.md` |
| GET list finetunes | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_finetunes.md` |
| PATCH update finetune | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_finetunes_finetune_id.md` |
| GET download dataset JSONL (self-hosted training) | `references/knowledge/api_docs/get_api_download_dataset_jsonl.md` |

## See also

When and why, in the knowledge: `references/improving_agents/techniques/model-swap-inside-a-class.md`, `references/levers/model.md`.
