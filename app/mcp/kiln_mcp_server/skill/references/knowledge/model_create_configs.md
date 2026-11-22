---
name: model_create_configs
description: |
  Run config creation, model parameters, naming rules, and comparison patterns. Load when: creating run configs, swapping models, setting parameters like temperature or thinking_level.
---
# Knowledge: Run Config Creation

All paths in this file are relative to the skill root (the directory containing SKILL.md).

## Knowledge Required

- `references/knowledge/model_work.md` — for shared rules (provider checking, batch approval), tier categories, and provider reference

## Shared Rules

**See `references/knowledge/model_work.md` → Shared Rules** for the full rules on `available_models` API usage, batch config approval, and checking connected providers. Those rules apply here too.

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

| Endpoint | Load |
|----------|------|
| Run configs — API catalog | `references/knowledge/api_docs/run_configs_api_list.md` |
| Providers & models — API catalog | `references/knowledge/api_docs/providers_models_api_list.md` |
| Runs — API catalog | `references/knowledge/api_docs/runs_api_list.md` |
| Prompts — API catalog | `references/knowledge/api_docs/prompts_api_list.md` |
| Tasks — API catalog | `references/knowledge/api_docs/tasks_api_list.md` |
| Tools & MCP — API catalog | `references/knowledge/api_docs/tools_mcp_api_list.md` |
| Evals — API catalog | `references/knowledge/api_docs/evals_api_list.md` |
| GET list available models | `references/knowledge/api_docs/get_api_available_models.md` |
| GET list provider models | `references/knowledge/api_docs/get_api_providers_models.md` |
| GET list run configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md` |
| POST create run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` |
| PATCH update run config | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_run_configs_run_config_id.md` |
| GET run config eval scores | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` |
| POST create MCP run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_mcp_run_config.md` |
| GET get task | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md` |
| GET list prompts | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md` |
| GET generate prompt | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md` |
| POST execute run | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md` |
| GET list runs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs.md` |
| POST create run (without executing model) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_runs.md` |

## URL Shape Note

`GET /api/projects/{pid}/tasks/{tid}/run_configs` — **no trailing slash**. A trailing `/` returns HTML 404 in some code paths. Also applies to `POST` on the same collection. If you get a 404 on a plural-list endpoint, retry the exact path from the endpoint doc (no trailing `/`).

## Before Creating a Config

1. **Find the exact Kiln model ID:** Use `GET /api/model_info/models` with `search` to fuzzy-match the model name (`references/knowledge/api_docs/get_api_model_info_models.md`), then `GET /api/model_info/model_details` to confirm details, pricing, and which providers support it (`references/knowledge/api_docs/get_api_model_info_model_details.md`).
2. **Verify the `(model_id, provider_id)` pair is actually served — not just that the provider is connected.** A connected provider does not mean every model exists on that provider; e.g. Cerebras is connected does not imply `gpt_oss_120b` is served on Cerebras. Use `available_models` and check the **pair**:

   Read `references/knowledge/api_docs/get_api_available_models.md`, then:
   `call_kiln_api("GET", "/api/available_models", jq_filter="[.[] | select(.provider_id == \"<provider_id>\") | .models[] | .id]")`

   The model_id you intend to POST must appear in that list. If it doesn't, either pick a different provider for that model or pick a different model on the connected provider — do **not** POST a `(model, provider)` pair you haven't confirmed in the response. `agent_overview.connected_providers` only tells you the provider has a valid API key; it does not tell you which models that key gives access to.

## Key Parameters

### Temperature
Controls randomness. Lower = more deterministic, higher = more creative.
- `0.0-0.3` — factual tasks, classification, structured extraction
- `0.5-0.7` — balanced (good default for most tasks)
- `0.8-1.0` — creative tasks, brainstorming

### Top P
Controls diversity of token selection. Usually leave at `1.0` unless you know what you're doing.

### Thinking Level
For reasoning models only. Controls how much "thinking" the model does before answering.
- `"low"` — quick reasoning, cheaper
- `"medium"` — balanced
- `"high"` — deep reasoning, most expensive
- `null` — use model defaults

### Structured Output Mode
How the model produces JSON output:
- `"json_schema"` — enforced by the provider (most reliable, not all models support it)
- `"json_instruction_and_object"` — instructed via prompt + `response_format: json_object`
- `"json_instruction"` — instructed via prompt only (least reliable, widest support)
- `"default"` — let Kiln decide based on model capabilities

### Tools Config
Whether the run config uses tools (MCP servers). Set to `null` for no tools, or configure which tool servers to use. See the Tools knowledge for details.

### Input Transform
Optionally reshape the task input before it reaches the model — e.g. **drop fields** the model shouldn't see, or render structured JSON as prose. Set `input_transform` to `{"type": "jinja", "template": "..."}`; the template sees one variable `input` (the parsed input object, so `{{ input.field_name }}`) and its rendered text becomes the first user message. Leave `null` (default) to pass the raw input through unchanged. The template is compiled when the config is saved — an invalid template returns 422.

## Kiln Name Validation

Resource names (run configs, specs, prompts, etc.) must follow these rules:
- **Forbidden characters:** `. , ; : = / \ ? % * | < >`
- **No consecutive whitespace or underscores**
- **No leading/trailing whitespace or underscores**
- **No newlines**

Key trap: model names like "GPT-4.1" contain a period — use "GPT4p1" or "GPT 4-1" in resource names instead.

## Getting the Prompt ID

Before creating a run config you need a `prompt_id`. Load the endpoint doc, then use this filter — the response is an object with `.prompts` and `.generators` arrays, not a flat array:

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/prompts",
  jq_filter=".prompts[0].id // .generators[0].id")
```

Use the returned ID as the `prompt_id` in the run config body. If `.prompts` is empty, fall back to the first generator ID (a built-in prompt builder).

> ⚠️ **Three hard prerequisites — all have caused bugs when skipped:**
>
> 1. **`prompt_id` must come from a real `GET /prompts` call on THIS task.** The string `"simple_prompt_builder"` is a generator name, not a valid prompt_id. Do NOT copy from an existing run config's `run_config_properties.prompt_id` — that's a second-hand reference (the prompt may be deleted or belong to a different task). Use the filter above; `.[] | {id, name}` is wrong (response is not a flat array).
> 2. **Name validation:** Periods, slashes, colons, and other forbidden chars (see "Kiln Name Validation" below) cause `Name: Value error, Name is invalid` (422). Model versions like "3.3" / "4.1" become "3p3" / "4p1". **Sanitize before POSTing.**
> 3. **`POST /prompts` and `GET /prompts` return the prompt ID in different shapes.** `GET /prompts` returns the prefixed form (`"id::197516709367"`) which is what `/run_configs` requires — use it as-is. `POST /prompts` returns the **bare** form (`"197516709367"`). If you just created the prompt this turn, either (a) re-fetch via `GET /prompts`, or (b) prepend `id::` to the POST-response `id`. Sending the bare form to `/run_configs` returns `422 Invalid prompt ID`.

## Creating a Run Config

```
# read first: references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
call_kiln_api("POST", "/api/projects/{project_id}/tasks/{task_id}/run_configs", body={
  "name": "GPT4p1 Mini Simple",  # period-free; "GPT-4.1" → "GPT4p1"
  "description": "Testing GPT-4.1 Mini with simple prompt at default temperature",
  "run_config_properties": {
    "type": "kiln_agent",
    "model_name": "gpt_4_1_mini",
    "model_provider_name": "openai",
    "prompt_id": "<UUID from GET /prompts above — NOT a literal>",
    "top_p": 1.0,
    "temperature": 0.7,
    "structured_output_mode": "json_schema",
    "thinking_level": null,
    "tools_config": null,
    "input_transform": null
  }
})
```

After creation, deep-link to the config: [View Config](/optimize/{pid}/{tid}/run_config/{rcid}).

## Provider Reference

**See `references/knowledge/model_work.md` → Provider Reference** for the full provider table with IDs and notes.
