---
name: model_work
description: |
  Model recommendation, gap analysis, tier taxonomy, MCP tool usage, provider reference, and cost estimation — everything you need to answer "what model should I use?" or "what models am I missing?" in one file. Loaded by Improve Task. When the answer is "create a run config with this model," hand off to references/knowledge/model_create_configs.md.
---
# Knowledge: Model Work (Selection, Assessment, Research)

One-file home for model questions: **recommend** (what to try), **assess** (what they already have), **research** (facts about tiers, pricing, providers). If a user's question is "what model?", "cheapest model?", "better model?", "what am I missing?", "upgrade to what?" — everything below applies.

When the next step is **building a run config** with a chosen model, hand off to `references/knowledge/model_create_configs.md`. When the next step is **reading scores to rank models**, hand off to `references/knowledge/eval_scores.md`.

## Model Info MCP Tools (the source of truth for all model facts)

All pricing, capability, and recommendation data comes from MCP tools — **never from priors, never from `available_models`**.

- **`model_info_featured()`** — curated ranked list with editorial notes, pricing, capabilities, providers. Start here for "what model should I use?", tier overviews, and provider-filtered browsing ("what's on Groq?" — filter the `providers` field).
- **`model_search(query)`** → **`model_info(model_id)`** — when the user names a specific model. Search first if you don't have the exact Kiln model ID.

> ⚠️ `model_search` is for a **specific named model**, not for enumerating a provider's catalog. Use `model_info_featured` + filter for provider browsing — it's one call instead of a search loop.

> ⚠️ **Model homepage / repo / paper / leaderboard URLs are not in MCP responses.** Don't emit them from priors — see `references/modes/improve_task.md` Response Contract item 7 (and the matching item in `references/modes/learn_about_kiln.md`) for the canonical rule and the "no curated link" phrasing.

## Shared Rules (apply to every turn in this file)

### `available_models` API — Provider Connectivity Only

The `available_models` API (via `call_kiln_api`) tells you which providers are connected and which models are accessible through them. It has **no pricing, no quality tiers, no recommendations** — do NOT use it for model selection. Use `model_info_featured` / `model_info` for that.

But: you MUST check `available_models` before creating a run config to confirm the chosen model is accessible through the user's connected providers.

### Check Connected Providers First (MANDATORY)

Connected providers come from the bootstrap `agent_overview.connected_providers`. Before proposing any models, surface them to the user ("I see OpenRouter and OpenAI connected — I'll stick to models on those unless you want to add more") and deep-link [Provider Settings](/settings/providers). Only recommend models from connected providers unless the user explicitly asks about adding one.

### Batch Run Config Creation (3+) Requires Approval

When creating **3+ run configs** in one plan, show the proposed list (model, tier, provider, key params) and wait for approval. 1–2 configs are fine to just create.

### Provider-Availability Caveat

TypeSafe AI is a classification-only provider (its Jev models return probabilities, never text); load `references/knowledge/typesafe_jev.md` before recommending it for anything.

When answering "what's the cheapest / best model?" without a task context, always caveat: "These recommendations depend on which providers you have connected" + deep-link to [Provider Settings](/settings/providers).

### Proportion Recommendations to Real Gaps

For "cheaper / reduce cost / faster" asks, the lead-recommendation gate lives in `references/modes/improve_task.md` Response Contract item 1 — quality-preserving mid-tier picks (Strong/Balanced or Fast tier; pull current names from `model_info_featured`, never name them from priors), never an Ultra-Fast/Cheapest floor model unless the user named a provider lock-in. When comparing speed or cost across options, name the multiplier (e.g. "~10× slower" / "~5× faster on Cerebras/Groq vs. native"), not the ordering. Options within ~2× are a tie; options ≥5× better lead unambiguously.

## API Docs

Load the relevant endpoint doc **before** each call.

| Endpoint | Load |
|----------|------|
| Providers & models — catalog | `references/knowledge/api_docs/providers_models_api_list.md` |
| Run configs — catalog | `references/knowledge/api_docs/run_configs_api_list.md` |
| Evals — catalog | `references/knowledge/api_docs/evals_api_list.md` |
| Tasks — catalog | `references/knowledge/api_docs/tasks_api_list.md` |
| GET list available models | `references/knowledge/api_docs/get_api_available_models.md` |
| GET available providers | `references/knowledge/api_docs/get_api_settings_available_providers.md` |
| GET list provider models | `references/knowledge/api_docs/get_api_providers_models.md` |
| GET run config eval scores | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` |
| GET eval configs score summary | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs_score_summary.md` |
| GET eval config score summary (per run config) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md` |

## Model Tier Categories

Use these tier names when discussing models. `model_info_featured()` returns the current ranked list; each model's `editorial_notes` and pricing place it in a tier.

| Tier | Description | When to use |
|------|-------------|-------------|
| **Frontier** | Best quality, highest cost | Quality is paramount |
| **Strong / Balanced** | Great quality, reasonable cost | Good default |
| **Fast / Cost-Effective** | Good quality, low cost | Speed/cost > perfection |
| **Ultra-Fast / Cheapest** | Acceptable quality, minimal cost | High-volume or simple tasks |
| **Reasoning** | Extended thinking, higher cost/latency | Complex multi-step problems |

Reasoning models use the `thinking_level` parameter (`"low"` / `"medium"` / `"high"`).

## Provider Reference

| Provider ID | Name | Notes |
|-------------|------|-------|
| `openai` | OpenAI | GPT models, best structured-output support |
| `anthropic` | Anthropic | Claude models |
| `gemini_api` | Google Gemini | Gemini models, fast |
| `openrouter` | OpenRouter | Aggregator — many models via one key (~10–30% markup) |
| `amazon_bedrock` | AWS Bedrock | Enterprise, multiple model families |
| `vertex` | Google Vertex | Enterprise Gemini |
| `cerebras` | Cerebras | Ultra-fast inference |
| `groq` | Groq | Fast inference |
| `fireworks_ai` | Fireworks AI | Fast open models |
| `together_ai` | Together AI | Open models |
| `ollama` | Ollama | Local, free |

## Open-Weight Models

For local/on-prem/privacy cases, check `open_weights` via `model_info(model_id)`. Search by family with `model_search("Llama")`, `model_search("Qwen")`, etc. For VRAM sizing: **N GB RAM ≈ N-billion-parameter model** at int8 (e.g., 32 GB → 32B). See also `references/knowledge/local_private_on_prem.md` for the end-to-end local workflow.

## Cost Estimation

Get live numbers from `model_info(model_id)` / `model_info_featured()` — fields `input_price_per_million` and `output_price_per_million`.

**Multipliers to apply:**
- **OpenRouter** adds ~10–30% markup over native provider pricing.
- **Reasoning models** at `thinking_level: "high"` can 2–5× the output token count (thinking tokens are billed).
- **Eval judge calls** add a per-item judge cost on top of each task call — pull the judge model's price from `model_info_featured()` rather than assuming one. Judges run offline/in batch, so a cheaper, slightly slower model is usually the right judge; factor its price in when estimating eval batch costs.

**Formula:**
```
cost_per_call   ≈ (input_tokens / 1M × input_price) + (output_tokens / 1M × output_price)
eval_batch_cost ≈ num_items × (cost_per_task_call + cost_per_judge_call)
```

Typical task: ~2K input, ~500 output. Multiply by dataset size for batch.

---

## Workflow A — Answer a Model Question (no task context)

User asks "what's cheapest?", "what's best?", "what's good for code generation?" without naming a task.

1. `model_info_featured()` → answer from results.
2. Apply the provider-availability caveat.
3. Use specific numbers (`~$0.003/call`, not `$$`).
4. Offer a follow-up: "If you tell me which task this is for, I can assess your existing configs and recommend specific upgrades."

**Proceed with best match + state assumption — never block pricing on task scope.** Pricing/tier answers are global (from `model_info_featured`). If the *only* ambiguity is "which task should I apply this to?", answer the pricing question first, then offer the task-specific follow-up. Do not stall with "which task?" before naming a model — that question is the follow-up, not the gate.

Do **not** load `references/knowledge/model_create_configs.md` for this workflow — there's no task to create a config on.

## Workflow B — Assess Existing Configs + Recommend (task context present)

User is on a task and asks "what do I have?", "what am I missing?", "what better models are available?", "upgrade my model?".

### Step 1 — Map Existing Configs

Use `agent_overview.run_configs.items` (name, model_name, model_provider) from the mode's bootstrap. Look up each model via `model_info(model_id)` and map each config to a tier per the table above.

Report coverage by tier, naming concrete models only from the Step 1 `model_info` lookups — e.g. "You have Frontier and Strong covered, but no Fast or Reasoning config yet." Never recite specific model names from memory; the catalog moves and the tiers are capability heuristics, not a fixed roster.

**If coverage is complete across relevant tiers, say so and stop** unless the user explicitly asked "what else is available?". Don't invent work.

### Step 2 — Discover Gaps

If tiers are missing or the user asks what's available:

1. `model_info_featured()` → curated ranked list.
2. Check connected providers (call `available_models`, or infer from existing configs — see Shared Rules).
3. Cross-reference: models in featured list, accessible via connected providers, that the user doesn't already have.
4. `model_info(model_id)` for detailed pricing/capabilities on interesting candidates.

### Step 3 — Present Recommendations

Task type affects tier relevance:
- Classification / extraction → rarely needs Frontier or Reasoning.
- Creative / generation / complex reasoning → benefit from Frontier / Reasoning.
- If all interesting gaps are in tiers irrelevant to the task, say so.

**Presentation format** (tier-grouped, task-specific):

| Model | ID | Tier | Why it matters (for THIS task) | ~Cost/call |
|-------|----|------|--------------------------------|------------|
| {model name} | `{model_id}` | {tier} | {why it matters for THIS task} | ~${cost/call} |

Group sections by relevance to the task ("High-Impact for Math (Reasoning Models)" vs. "Strong General Models You're Missing"). Lead with the highest-impact group.

### Step 4 — Default Action After Recommendation (execute, don't stop)

After recommending a model, **immediately create a run config for it** — do not end on a recommendation. A recommendation without a config is not a usable answer.

1. Load `references/knowledge/model_create_configs.md`.
2. POST the new run config with the recommended model. Use a sanitized name and a real `prompt_id` from `GET /api/projects/{pid}/tasks/{tid}/prompts` (never the literal generator name like `simple_prompt_builder`).
3. Include the `/optimize/{pid}/{tid}/run_config/{rcid}` deep-link in the response.
4. If the POST fails (provider not connected, 422, etc.), fall back to `/optimize/{pid}/{tid}/run_config/create` with the recommended model as a UI suggestion.

## Workflow C — Ranking / "Which is best?" when evals exist or are missing

If the user asks "which model is best for this task?" or "what's the cheapest model that still passes?":

- **Evals + scores exist** → hand off to `references/knowledge/eval_scores.md` for the scorecard + Compare link flow.
- **Specs configured, scores empty** (eval configs exist but no eval runs completed — `dataset_size: 0` everywhere) → hand off to the "Specs configured, scores empty — the Compare-link fallback" section of `references/knowledge/eval_scores.md`. Produce a cost ladder + Compare link, do not stop at "no scores yet."
- **No evals yet** → hand off to the "No evals yet — minimum viable path" section of `references/knowledge/eval_scores.md` (Eval Builder → judge → run eval → re-check). Do not stop at "I can't help"; return the minimum viable path as the answer.

## UI Deep Links

| Action | Path |
|--------|------|
| View connected providers | `/settings/providers` |
| Add provider | `/settings/providers` |
| Add custom model | `/settings/providers/add_models` |
| View all run configs | `/optimize/{pid}/{tid}` |
| Create run config (UI) | `/optimize/{pid}/{tid}/run_config/create` |
| Single run config | `/optimize/{pid}/{tid}/run_config/{rcid}` |
