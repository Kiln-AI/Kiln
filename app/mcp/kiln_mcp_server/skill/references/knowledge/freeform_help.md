---
name: freeform_help
description: |
  Fallback knowledge for ad-hoc problem solving when no established knowledge file matches the user's need. Discouraged — prefer specific knowledge files when possible.
---
# Freeform Help

The user's request doesn't clearly match any specific knowledge file. Assess what they need, load relevant knowledge, and improvise a solution. This is a **discouraged fallback** — if a specific knowledge file exists for the topic, load that instead.

## Knowledge Required

These are reference knowledge files. Load as needed based on what the user is asking about.

| Knowledge | What It Provides | Load |
|-----------|-----------------|------|
| **Evals** | What specs are, types, eval pipeline hierarchy, agent's role with specs | `references/knowledge/specs_and_evals.md` |
| **Eval Scores & Scorecards** | Score reading patterns, jq filters, scorecard building, comparison tables | `references/knowledge/eval_scores.md` |
| **Model Work** | Recommend models, assess existing configs, tier guide, pricing, provider reference, cost estimation. **Use Model Info MCP tools** (`model_info_featured`, `model_info`, `model_search`) for live data first — see SKILL.md → MCP Tools | `references/knowledge/model_work.md` |
| **Run Config Creation** | Creating run configs, model parameters, naming validation | `references/knowledge/model_create_configs.md` |
| **Tools** | MCP tool servers — local, remote, Kiln task tools | `references/knowledge/tools.md` |
| **RAG** | Document retrieval — document library and RAG setup | `references/knowledge/rag.md` |
| **Docs Index** | Official Kiln help documentation — index of all articles with descriptions | `references/docs/docs_index.md` |
| **Provider Setup** | Provider/API key setup — triage, non-technical explanations, troubleshooting | `references/knowledge/provider_setup.md` |
| **Prompt Audit** | Systematic prompt review checklist (clarity, format, edge cases, examples) | `references/knowledge/prompt_audit.md` |

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details. Use the domain catalogs below to find the right endpoint doc, then read it at `references/knowledge/api_docs/<endpoint>.md`. All endpoint docs referenced across knowledge files are listed below.

**Domain catalogs** — full indexes (browse when the table below is not enough):

| Area | Catalog |
|------|---------|
| Eval Builder | `references/knowledge/api_docs/copilot_api_list.md` |
| Documents & RAG | `references/knowledge/api_docs/documents_api_list.md` |
| Evals | `references/knowledge/api_docs/evals_api_list.md` |
| Fine-tuning | `references/knowledge/api_docs/finetuning_api_list.md` |
| Projects | `references/knowledge/api_docs/projects_api_list.md` |
| Prompts | `references/knowledge/api_docs/prompts_api_list.md` |
| Providers & models | `references/knowledge/api_docs/providers_models_api_list.md` |
| Run configs | `references/knowledge/api_docs/run_configs_api_list.md` |
| Runs | `references/knowledge/api_docs/runs_api_list.md` |
| Settings & utilities | `references/knowledge/api_docs/settings_utilities_api_list.md` |
| Skills | `references/knowledge/api_docs/skills_api_list.md` |
| Specs | `references/knowledge/api_docs/specs_api_list.md` |
| Synthetic data | `references/knowledge/api_docs/synthetic_data_api_list.md` |
| Tasks | `references/knowledge/api_docs/tasks_api_list.md` |
| Tools & MCP | `references/knowledge/api_docs/tools_mcp_api_list.md` |

## Suggested Questions

1. **What are you trying to accomplish?** Get the concrete goal, not just the symptom.
2. **Have you tried any of these?** Briefly describe 2-3 knowledge areas that seem closest, to check if one actually fits.
3. **What does success look like?** Helps scope the work.

## Approaches

### Assess and Narrow

Listen to the user's description. Check if the problem actually maps to an existing knowledge file that was missed during initial routing — if so, load that knowledge file instead.

### Build an Ad-Hoc Plan

If no knowledge file fits, break the problem into steps using available knowledge:

1. Identify which knowledge files and API endpoints are relevant
2. Load them as needed
3. Work through the problem step by step, reporting progress

### Execute and Adapt

Work through the plan. If mid-execution a specific knowledge file would help, load it.

## Data Quality Note

`references/docs/` files are end-user documentation and a **lower quality signal** than reference knowledge files. Prefer knowledge files when both cover a topic. Use doc articles primarily for their `online_url` to link the user to further reading.
