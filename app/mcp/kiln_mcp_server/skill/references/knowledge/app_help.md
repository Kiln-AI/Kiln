---
name: app_help
description: |
  Knowledge for troubleshooting Kiln errors, provider issues, configuration problems, and general "how do I..." questions. Loaded by the Learn About Kiln mode.
---
# App Help & Troubleshooting

Reference knowledge for handling problems with Kiln itself — error messages, unexpected behavior, configuration issues, and general "how do I..." questions.

## Knowledge Required

- `references/docs/docs_index.md` — index of all official Kiln help articles. Load this first for any "how do I..." question, then load the matching article.
- `references/knowledge/provider_setup.md` — when the issue is provider/API key related
- `references/knowledge/specs_and_evals.md` — when the user asks "what is an eval?", "how do evals work?", or "what is Kiln Pro?" (the Kiln Pro blurb lives in this file)
- `references/knowledge/rag.md` — when the user asks about RAG or document search
- `references/knowledge/tools.md` — when the user asks about tools or integrations
- `references/knowledge/model_work.md` — when the user asks about models
- `references/knowledge/data_guides.md` — when the user asks about data guides or making synthetic inputs realistic
- `references/knowledge/judge_types.md` — when the user asks about eval/judge types, code evals, deterministic checks, or "what kinds of evals are there"

## API Docs

Load the relevant endpoint doc **before** making each API call. When you need to discover endpoints, start from the **Catalog** rows at the top of the table; each catalog lists paths to per-endpoint detail files.

| Endpoint | Load |
|----------|------|
| **Catalog:** Settings & utilities (ping, settings, logs, entitlements) | `references/knowledge/api_docs/settings_utilities_api_list.md` |
| **Catalog:** Providers & models (available models, API keys, user models) | `references/knowledge/api_docs/providers_models_api_list.md` |
| **Catalog:** Projects (list / get / create projects) | `references/knowledge/api_docs/projects_api_list.md` |
| GET `/ping` (server health) | `references/knowledge/api_docs/get_ping.md` |
| GET `/api/settings` (read settings) | `references/knowledge/api_docs/get_api_settings.md` |
| GET `/api/settings/{item_id}` (single setting item) | `references/knowledge/api_docs/get_api_settings_item_id.md` |
| GET `/api/projects` (list projects) | `references/knowledge/api_docs/get_api_projects.md` |
| GET `/api/projects/{project_id}/tasks` (list tasks) | `references/knowledge/api_docs/get_api_projects_project_id_tasks.md` |
| GET `/api/available_models` (connectivity / which models appear) | `references/knowledge/api_docs/get_api_available_models.md` |
| GET `/api/settings/available_providers` (which providers can be configured) | `references/knowledge/api_docs/get_api_settings_available_providers.md` |
| GET `/api/check_entitlements` | `references/knowledge/api_docs/get_api_check_entitlements.md` |

## Suggested Questions

1. **What's happening?** "What error or issue are you seeing?" (get the error message, screenshot, or description)
2. **What were you trying to do?** Context helps narrow the problem.

## Troubleshooting Approaches

### Diagnose the Problem Category

Based on the user's description, determine which category the issue falls into:
- **Provider / API key issues** — "stuck on the API key screen", "how do I connect a provider", "unauthorized / 401 error", "models aren't showing up"
- **General errors** — server issues, unexpected behavior, configuration problems
- **"How do I..." questions** — conceptual questions about Kiln features

### Handle Provider / API Key Issues

If the problem is provider-related, load `references/knowledge/provider_setup.md` — it has the full triage flow, non-technical explanations, IT handoff checklists, and troubleshooting tables.

### Handle General Errors

For errors not related to providers:

1. **Read the error message carefully** — many Kiln errors are descriptive.
2. **If it's a model / provider connectivity symptom** (missing models, "provider not available", no response from a specific model), check providers first — this diagnoses the common case before a server-level check:
Read `references/knowledge/api_docs/get_api_available_models.md`, then:
`call_kiln_api("GET", "/api/available_models", jq_filter="[.[] | .provider_id] | unique")`
3. **Only if the symptom looks server-level** (total unresponsiveness, all endpoints failing), check Kiln server health:
Read `references/knowledge/api_docs/get_ping.md`, then:
`call_kiln_api("GET", "/api/ping")`
4. **Deep-link to relevant settings:**
   - [Provider Settings](http://localhost:8757/settings/providers) — for connectivity issues
   - [Add/manage tools](http://localhost:8757/tools/{project_id}/add_tools) — for tool configuration issues
   - [Task settings](http://localhost:8757/settings/edit_task/{project_id}/{task_id}) — for task configuration issues
5. **If you can't diagnose it:** Suggest checking server logs or searching [Kiln docs](https://docs.kiln.tech/)

### Handle "How Do I..." Questions

For conceptual or documentation questions:

1. **Load `references/docs/docs_index.md`** and find the article that matches the user's question.
2. **Load the matching doc article** (e.g. `references/docs/agents.md`, `references/docs/evals-and-specs/evaluations.md`). Answer from the article content — this is the authoritative source.
3. **Share the article's `online_url`** from its YAML frontmatter so the user can read more.
4. **Fall back to knowledge files** if no doc article covers the topic:
   - Evals / Eval Builder → `references/knowledge/specs_and_evals.md`
   - Data guides / synthetic data realism → `references/knowledge/data_guides.md`
   - Eval/judge types, code evals, deterministic checks → `references/knowledge/judge_types.md`
   - RAG → `references/knowledge/rag.md`
   - Tools → `references/knowledge/tools.md`
   - Models → `references/knowledge/model_work.md`

Provide a concise explanation with key concepts and deep-link to the relevant UI page.

## Data Quality Note

`references/docs/` files are end-user documentation written for the Kiln website. They are a **lower quality signal** than reference knowledge files. When both a doc article and a knowledge file cover the same topic, prefer the knowledge file for accuracy and use the doc article's `online_url` for linking the user to further reading.
