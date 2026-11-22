---
name: local_private_on_prem
description: |
  Knowledge for moving an agent to open-weight models for privacy, local deployment, or on-prem requirements. Loaded by the Improve Task mode.
---
# Local / Private / On-Prem

Reference knowledge for moving agents to open-weight models for privacy, local deployment, or on-premises requirements.

## Knowledge Required

- `references/knowledge/model_work.md` — for open-weight model suggestions, VRAM-to-parameter sizing, tier guide, and provider reference
- `references/knowledge/provider_setup.md` — when the user needs to connect OpenRouter or another provider
- `references/knowledge/tools.md` — when the user needs dedicated MCP tools as an advanced fallback
- `references/modes/improve_task.md` — for running systematic model comparisons

## API Docs

Load the relevant endpoint doc **before** making each API call. Use the domain catalogs below to find any endpoint not listed in the table.

| Domain | Catalog |
|--------|---------|
| Run configs | `references/knowledge/api_docs/run_configs_api_list.md` |
| Providers & models | `references/knowledge/api_docs/providers_models_api_list.md` |
| Runs | `references/knowledge/api_docs/runs_api_list.md` |
| Tools & MCP | `references/knowledge/api_docs/tools_mcp_api_list.md` |

| Endpoint | Load |
|----------|------|
| GET run configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md` |
| POST create run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` |
| PATCH update run config | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_run_configs_run_config_id.md` |
| GET per-config eval scores | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` |
| GET available models | `references/knowledge/api_docs/get_api_available_models.md` |
| GET list provider models | `references/knowledge/api_docs/get_api_providers_models.md` |
| POST connect Ollama | `references/knowledge/api_docs/post_api_provider_ollama_connect.md` |
| POST execute run | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md` |
| POST create finetune | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_finetunes.md` |

## Background: Privacy, Local Inference, and On Prem

Most people who build/deploy AI agents use cloud service providers for their AI inference (OpenAI, OpenRouter, Anthropic, Google Vertex, AWS, etc). This makes it easy to deploy as they don't need to manage GPUs and inference services. However, this means a third party has access to all of your prompts, inputs and outputs.

There are several use cases where an agent owner may want to control where inference happens:
- Corporations with privacy or legal requirements: data must not leave their servers/infrastructure. Common for larger corporations and sensitive data (health, legal).
- App developer who wants to add local AI to their app: build an app that runs on the user's machine, so no privacy concerns or cloud hosting costs.
- Hobbyist privacy enthusiast: run locally on their own computer. Often a Mac with ample unified memory, or a PC with consumer GPU.

## Approach: Open-weight models

Generally the solution is to move off of proprietary close-weight models that can only be accessed from cloud providers, and instead use open-weight models. This may require experimenting with several models to find one that has acceptable quality comparable to the models they were using.

In some cases we may need to change agent design (tools/sub-tasks) or even fine-tune, but these are more rare. Typically we want to focus on selecting open-weight models.

## Suggested Questions

Send the user a message asking for more information. Use context from earlier chat comments and fetched provider data to filter or update these:

1. **Why private?** On-prem enterprise requirements? Building an app with embedded local models? Personal use on own machine?
2. **Okay with hosted experimentation?** "Are you okay using a hosted service like OpenRouter to find an ideal model, and moving to private/local after?"
3. **Local vs VPC?** When they say "on prem" do they really mean local, or a virtual private cloud?
4. **Size limit?** Any limit to the model size? Can say "no limit", maximum parameter count (8B, 32B, etc), or maximum VRAM/GPU-RAM size (64GB, 256GB, etc).

**Converting VRAM to maximum parameters**: see `references/knowledge/model_work.md` → Open-Weight Models for the conversion rule.

## Approaches

### Check if Already Done

It's possible the user is already set up for open weight models. List run configs and check if the default (starred) config already uses open-weight models.

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`, then:
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/run_configs", jq_filter="[.[] | {name, model: .run_config_properties.model_name, provider: .run_config_properties.model_provider_name, starred}]")

If already using open-weight models, skip to explaining next steps.

### Special Case: VPC

If the user really means VPC, the approach is different — they'll use the same cloud provider APIs but within their private infrastructure. Guide them to check their provider's VPC/private endpoint documentation.

### Connect Provider

- Skip if they already have OpenRouter connected or said they wouldn't connect another provider
- If they need it: ask them to connect OpenRouter in the app, at [Providers](http://localhost:8757/settings/providers) — this connection cannot connect a provider key. Load `references/knowledge/provider_setup.md` for detailed guidance.
- If they only have providers with closed weight models (OpenAI, Anthropic, Gemini API): inform them we'll need either Ollama or a provider with open-weight models.

### Run Experiments

Plan and run a set of experiments using open-weight models. Read `references/modes/improve_task.md` for how to run the experiments, using these constraints:
- Only use models they have available
- Only use models that fit their RAM/parameter limit
- Only use open-weight models — use `GET /api/model_info/models` with `open_weights=true`, or find the model with `search` and check `open_weights` in `GET /api/model_info/model_details`. See also `references/knowledge/model_work.md` → Open-Weight Models for size guidance

### Select New Default

If the user has a new winner, offer to make it their new default run config.

### Explain Next Steps

```
Great, we've found an agent design that can be deployed [locally/on-prem/embedded]!

Here are some next steps to deploying it

- **Review the license of your selected model**. AI models aren't as simple as open-source code. Double check the license of the model you want to use is compatible with your goals.
- **Deploy It**:
  - Enterprise: work with IT to deploy this model using tooling like [VLLM](https://github.com/vllm-project/vllm).
  - Local projects: Try [Ollama](https://ollama.com/), [LlamaBarn](https://github.com/ggml-org/LlamaBarn), or [LM Studio](https://lmstudio.ai/)
  - Embedding into an app: depends on your platform and goals. Go grab an engineer ;)
```

### Advanced Options

Only offer these if model-selection alone didn't work well:
- Larger models: if they set the size limit, ask if it can be removed
- Agent design: adding sub-agents to keep the context window focused
- Tools: add dedicated MCP tools for harder elements. Load `references/knowledge/tools.md`
- Fine-tuning: use Kiln's fine-tuning to tune to this task
