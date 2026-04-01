---
status: complete
---

# 

I want to improve our OpenAPI spec for the app/desktop/desktop_server.py (which extends libs/server project so we’ll need to update both).

The report below highlights issues.

critical: I want to approve every functional change (renaming endpoint, changing types, etc) when creating the functional spec. Doc only updates don’t need to be approved.

# OpenAPI Spec Analysis Report — Kiln AI API v0.26.0
**Purpose:** This report identifies issues that make the spec harder for agents to use, with actionable fixes for each issue.

## Executive Summary
| **Metric** | **Count** |
|:-:|:-:|
| Total operations | 173 |
| Operations missing description | 150 (87%) |
| Parameters missing description | 315 across 150 ops |
| Schemas missing description | 172 of 263 (65%) |
| Schema properties missing description | 788 |
| Duplicate summaries (ambiguous) | 1 pair |
| HTTP method misuse (GET for mutations) | 5 ops |
| Path naming inconsistencies | 3 patterns |

## Issue 1: Missing Operation Descriptions (Critical)
**87% of operations have no** **description** — only a summary. Summaries are too short to give an agent the context it needs to choose between similar endpoints, understand side effects, or know prerequisites.
### Operations That Have Descriptions (use as style reference)
These are the only 23 operations with descriptions. They show the right level of detail:
POST /api/projects/{project_id}/tasks/{task_id}/runs
  "Create a TaskRun directly without running a model."

GET /api/projects/{project_id}/tasks/{task_id}/rating_options
  "Generates an object which determines which rating options should be shown for a given dataset item."

POST /api/projects/{project_id}/tasks/{task_id}/spec_with_copilot
  "Create a spec using Kiln Copilot. This endpoint uses Kiln Copilot to create a spec with: 1. An eval..."
### All Operations Missing Descriptions
Every operation below needs a description field added. Descriptions should clarify: what the operation does, when to use it vs. similar endpoints, any prerequisites, and side effects.
**Projects & Tasks**
POST   /api/project                          — Create Project
PATCH  /api/project/{project_id}             — Update Project
GET    /api/projects                         — Get Projects
GET    /api/projects/{project_id}            — Get Project
DELETE /api/projects/{project_id}            — Delete Project
POST   /api/import_project                   — Import Project
POST   /api/projects/{project_id}/task       — Create Task
PATCH  /api/projects/{project_id}/task/{task_id}   — Update Task
DELETE /api/projects/{project_id}/task/{task_id}   — Delete Task
GET    /api/projects/{project_id}/tasks      — Get Tasks
GET    /api/projects/{project_id}/tasks/{task_id}  — Get Task
**Prompts & Specs**
POST   /api/projects/{project_id}/task/{task_id}/prompt           — Create Prompt
GET    /api/projects/{project_id}/task/{task_id}/prompts          — Get Prompts
PATCH  /api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}  — Update Prompt
DELETE /api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}  — Delete Prompt
GET    /api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_id} — Generate Prompt
POST   /api/projects/{project_id}/tasks/{task_id}/spec            — Create Spec
GET    /api/projects/{project_id}/tasks/{task_id}/specs           — Get Specs
GET    /api/projects/{project_id}/tasks/{task_id}/specs/{spec_id} — Get Spec
PATCH  /api/projects/{project_id}/tasks/{task_id}/specs/{spec_id} — Update Spec
DELETE /api/projects/{project_id}/tasks/{task_id}/specs/{spec_id} — Delete Spec
**Runs**
GET    /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}   — Get Run
DELETE /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}   — Delete Run
PATCH  /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}   — Update Run
GET    /api/projects/{project_id}/tasks/{task_id}/runs            — Get Runs
GET    /api/projects/{project_id}/tasks/{task_id}/runs_summaries  — Get Runs Summary
POST   /api/projects/{project_id}/tasks/{task_id}/runs/delete     — Delete Runs
POST   /api/projects/{project_id}/tasks/{task_id}/run             — Run Task
POST   /api/projects/{project_id}/tasks/{task_id}/runs/edit_tags  — Edit Tags (runs)
POST   /api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload — Bulk Upload
POST   /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/run_repair — Run Repair
POST   /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/repair     — Post Repair Run
GET    /api/projects/{project_id}/tasks/{task_id}/tags            — Get Tags
**Evals**
POST   /api/projects/{project_id}/tasks/{task_id}/eval            — Create Eval
GET    /api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}  — Get Eval
DELETE /api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}  — Delete Eval
PATCH  /api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}  — Update Eval
GET    /api/projects/{project_id}/tasks/{task_id}/evals           — Get Evals
GET    .../eval/{eval_id}/eval_configs                            — Get Eval Configs
GET    .../eval/{eval_id}/eval_config/{eval_config_id}            — Get Eval Config
POST   .../eval/{eval_id}/create_eval_config                      — Create Eval Config
GET    .../eval/{eval_id}/eval_config/{eval_config_id}/run_task_run_eval  — Run Eval Config
GET    .../eval/{eval_id}/run_eval_config_eval                    — Run Eval Config Eval
GET    .../eval/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results — Get Eval Run Results
GET    .../eval/{eval_id}/progress                                — Get Eval Progress
GET    .../eval/{eval_id}/eval_config/{eval_config_id}/score_summary — Get Eval Config Score Summary
GET    .../eval/{eval_id}/eval_configs_score_summary              — Get Eval Configs Score Summary
GET    .../run_config/{run_config_id}/eval_scores                 — Get Run Config Eval Scores
POST   .../eval/{eval_id}/set_current_eval_config/{eval_config_id} — Set Default Eval Config
**Run Configs**
GET    /api/projects/{project_id}/tasks/{task_id}/run_configs/    — Get Run Configs
POST   /api/projects/{project_id}/tasks/{task_id}/task_run_config — Create Task Run Config
PATCH  /api/projects/{project_id}/tasks/{task_id}/run_config/{run_config_id} — Update Run Config
POST   /api/projects/{project_id}/tasks/{task_id}/mcp_run_config  — Create Mcp Run Config
**Synthetic Data Generation**
POST   .../generate_categories   — Generate Categories
POST   .../generate_inputs       — Generate Samples
POST   .../generate_sample       — Generate Sample
POST   .../generate_qna          — Generate Qna Pairs
POST   .../save_sample           — Save Sample
POST   .../save_qna_pair         — Save Qna Pair
**Documents**
POST   /api/projects/{project_id}/documents/bulk          — Create Documents Bulk
GET    /api/projects/{project_id}/documents               — Get Documents
GET    /api/projects/{project_id}/documents/tags          — Get Document Tags
GET    /api/projects/{project_id}/documents/tag_counts    — Get Document Tag Counts
GET    /api/projects/{project_id}/documents/{document_id} — Get Document
PATCH  /api/projects/{project_id}/documents/{document_id} — Patch Document
DELETE /api/projects/{project_id}/documents/{document_id} — Delete Document
POST   /api/projects/{project_id}/documents/edit_tags     — Edit Tags (documents)
**Finetune, Providers, Settings, Copilot, Tools, Skills**
POST   /api/finetune                     — Create Finetune
GET    /api/finetune_providers           — Get Finetune Providers
GET    /api/available_models             — Get Available Models
GET    /api/available_embedding_models   — Get Available Embedding Models
GET    /api/available_reranker_models    — Get Available Reranker Models
POST   /api/copilot/clarify_spec         — Clarify Spec
POST   /api/copilot/refine_spec          — Refine Spec
POST   /api/copilot/generate_batch       — Generate Batch
POST   /api/copilot/question_spec        — Question Spec
POST   /api/copilot/refine_spec_with_question_answers — Submit Question Answers
GET    /api/projects/{project_id}/available_tools       — Get Available Tools
GET    /api/projects/{project_id}/available_tool_servers — Get Available Tool Servers
GET    /api/projects/{project_id}/kiln_task_tools       — Get Kiln Task Tools
GET    /api/projects/{project_id}/tool_servers/{tool_server_id}        — Get Tool Server
DELETE /api/projects/{project_id}/tool_servers/{tool_server_id}        — Delete Tool Server
GET    /api/projects/{project_id}/tool_servers/{tool_server_id}/config — Get Tool Server Config
POST   /api/projects/{project_id}/connect_remote_mcp   — Connect Remote Mcp
PATCH  /api/projects/{project_id}/edit_remote_mcp/{tool_server_id}    — Edit Remote Mcp
POST   /api/projects/{project_id}/connect_local_mcp    — Connect Local Mcp
PATCH  /api/projects/{project_id}/edit_local_mcp/{tool_server_id}     — Edit Local Mcp
POST   /api/projects/{project_id}/kiln_task_tool        — Add Kiln Task Tool
PATCH  /api/projects/{project_id}/edit_kiln_task_tool/{tool_server_id} — Edit Kiln Task Tool
GET    /api/projects/{project_id}/skills                — Get Skills
POST   /api/projects/{project_id}/skills                — Create Skill
GET    /api/projects/{project_id}/skills/{skill_id}     — Get Skill
PATCH  /api/projects/{project_id}/skills/{skill_id}     — Update Skill
GET    /api/projects/{project_id}/skills/{skill_id}/content — Get Skill Content
GET    /api/demo_tools                  — Get Demo Tools
POST   /api/demo_tools                  — Set Demo Tools
GET    /api/projects/{project_id}/search_tools          — Get Search Tools
GET    /api/select_kiln_file            — Select Kiln File
GET    /api/open_project_folder         — Open Project Folder
GET    /api/open_logs                   — Open Logs
GET    /api/provider/ollama/connect     — Connect Ollama Api
GET    /api/provider/docker_model_runner/connect — Connect Docker Model Runner Api
GET    /api/providers                   — Get Providers
GET    /api/providers/{provider_name}   — Get Provider
GET    /api/providers/{provider_name}/models — Get Provider Models

## Issue 2: Missing Parameter Descriptions (Critical)
315 path/query parameters have no description. The most pervasive is project_id, task_id, and similar IDs appearing across nearly every endpoint without explanation of what type of value is expected (UUID? string slug?). Other flagged parameters:
| **Parameter** | **Appears on** | **Fix** |
|:-:|:-:|:-:|
| project_id | ~120 ops | Add: "The unique identifier (UUID) of the project." |
| task_id | ~90 ops | Add: "The unique identifier (UUID) of the task within the project." |
| run_id | ~15 ops | Add: "The unique identifier (UUID) of the task run." |
| eval_id | ~20 ops | Add: "The unique identifier (UUID) of the eval." |
| eval_config_id | ~10 ops | Add: "The unique identifier (UUID) of the eval configuration." |
| run_config_id | ~10 ops | Add: "The unique identifier (UUID) of the run configuration." |
| prompt_id | ~5 ops | Add: "The unique identifier (UUID) of the prompt." |
| spec_id | ~5 ops | Add: "The unique identifier (UUID) of the spec." |
| tool_server_id | ~10 ops | Add: "The unique identifier (UUID) of the tool server." |
| skill_id | ~5 ops | Add: "The unique identifier (UUID) of the skill." |
| document_id | ~5 ops | Add: "The unique identifier (UUID) of the document." |
| tool_id | ~3 ops | Add: "The tool identifier string as returned by the tools list endpoints." |
| job_id | 2 ops | Add: "The unique identifier of the prompt optimization job." |
| prompt_optimization_job_id | 1 op | Add: "The unique identifier of the prompt optimization job." |
| update_status | 1 op | Add: "If true, fetches the latest status from the remote Kiln server for in-progress jobs before returning." |
| run_config_ids | 1 op | Add: "Comma-separated list of run config IDs to evaluate. Mutually exclusive with all_run_configs." |
| all_run_configs | 1 op | Add: "If true, runs the eval against all run configs for this task. Mutually exclusive with run_config_ids." |
| enable_demo_tools | 1 op | Add: "If true, enables demo tools for testing; if false, disables them." |
| tags (documents) | 1 op | Add: "Optional comma-separated list of tags to filter documents by." |
| title (select_kiln_file) | 1 op | Add: "The title to display in the file picker dialog." |
| project_path | 1 op | Add: "Absolute path to the project directory to import." |

## Issue 3: Naming Inconsistencies (High)
Agents navigating the spec will encounter the same concept with different naming conventions, making it unclear whether they refer to the same resource.
### 3a: Singular vs. Plural Path Segments —/task vs. /tasks
The collection and item paths use inconsistent prefixes. Standard REST convention is to use the plural noun for both the collection (/tasks) and item (/tasks/{id}). The spec mixes singular and plural:
| **Inconsistent (singular)** | **Should match plural form** |
|:-:|:-:|
| POST /api/projects/{project_id}/task | Create task — uses singular |
| PATCH /api/projects/{project_id}/task/{task_id} | Update task — uses singular |
| DELETE /api/projects/{project_id}/task/{task_id} | Delete task — uses singular |
| POST /api/projects/{project_id}/task/{task_id}/prompt | Create prompt — uses singular task |
| GET /api/projects/{project_id}/task/{task_id}/prompts | Get prompts — uses singular task |
| GET /api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_id} | Generate prompt — uses singular task |
The read (GET) endpoints use /tasks/{task_id} while write (POST/PATCH/DELETE) endpoints use /task/{task_id}. Fix: standardize all task-scoped paths to /tasks/{task_id}.
### 3b: Singular vs. Plural Path Segments —/spec vs. /specs
Same pattern exists for specs:
| **Path** | **Issue** |
|:-:|:-:|
| POST /api/projects/{project_id}/tasks/{task_id}/spec | Create uses singular |
| POST /api/projects/{project_id}/tasks/{task_id}/spec_with_copilot | Uses singular prefix |
| GET /api/projects/{project_id}/tasks/{task_id}/specs | List uses plural |
| GET /api/projects/{project_id}/tasks/{task_id}/specs/{spec_id} | Item uses plural |
Fix: standardize to /specs for both create and list/item paths.
### 3c:run_config vs. task_run_config vs. mcp_run_config
Three path segments that all refer to run configurations:
GET    /api/projects/{project_id}/tasks/{task_id}/run_configs/        ← plural collection
POST   /api/projects/{project_id}/tasks/{task_id}/task_run_config     ← singular, prefixed
PATCH  /api/projects/{project_id}/tasks/{task_id}/run_config/{id}     ← singular, no prefix
POST   /api/projects/{project_id}/tasks/{task_id}/mcp_run_config      ← singular, different prefix
An agent cannot tell whether task_run_config and run_config are the same resource type. Fix: use a single consistent path segment (e.g., /run_configs) with type differentiation via the request body, or use clearly scoped paths like /run_configs/task and /run_configs/mcp.

## Issue 4: Ambiguous Duplicate Summaries (Medium)
Two endpoints share the summary "Edit Tags" with no description to distinguish them:
| **Method** | **Path** | **Summary** |
|:-:|:-:|:-:|
| POST | /api/projects/{project_id}/tasks/{task_id}/runs/edit_tags | Edit Tags |
| POST | /api/projects/{project_id}/documents/edit_tags | Edit Tags |
An agent seeing both in a tool list cannot distinguish them without looking at the full URL. Fix:
* Change summaries to "Edit Run Tags" and "Edit Document Tags" respectively.
* Add descriptions explaining what "editing tags" means (replace all? add/remove specific tags?).

⠀
## Issue 5: HTTP Method Misuse — GET for Mutations (Medium)
The following operations use GET but trigger side effects (execution, connection establishment). GET should be idempotent and side-effect-free. An agent following standard REST semantics will avoid calling these for execution:
| **Path** | **Summary** | **Issue** |
|:-:|:-:|:-:|
| GET .../extractor_configs/{id}/run_extractor_config | Run Extractor Config | Executes an extractor — should be POST |
| GET .../rag_configs/{id}/run | Run Rag Config | Executes a RAG config — should be POST |
| GET /api/provider/ollama/connect | Connect Ollama Api | Establishes a connection — should be POST |
| GET /api/provider/docker_model_runner/connect | Connect Docker Model Runner Api | Establishes a connection — should be POST |
| GET .../eval_config/{id}/run_task_run_eval | Run Eval Config | Runs evaluations — should be POST |
| GET .../run_eval_config_eval | Run Eval Config Eval | Runs evaluations — should be POST |
Fix: change these to POST. At minimum, add descriptions explicitly warning that despite using GET, these operations trigger execution.

## Issue 6:run vs. runs — Execution vs. Storage Confusion (High)
The endpoints POST .../run and POST .../runs are easily confused by agents:
| **Path** | **Summary** | **Description** |
|:-:|:-:|:-:|
| POST /api/projects/{project_id}/tasks/{task_id}/run | Run Task | **MISSING** — actually invokes a model |
| POST /api/projects/{project_id}/tasks/{task_id}/runs | Create Task Run | "Create a TaskRun directly without running a model." |
These are semantically opposite actions (one runs a model, one stores a pre-computed result) but their URLs differ by only an s. An agent will very likely call the wrong one.
Fix: Add descriptions to both endpoints immediately. Consider renaming the execution endpoint to make the distinction explicit, e.g., /tasks/{task_id}/execute or /tasks/{task_id}/run_inference.

## Issue 7: Repair Endpoint Duplication (Medium)
Two endpoints exist for repairing a run with no description on either:
| **Path** | **Summary** |
|:-:|:-:|
| POST .../runs/{run_id}/run_repair | Run Repair |
| POST .../runs/{run_id}/repair | Post Repair Run |
It is unclear whether these are duplicates, one is deprecated, or they serve different purposes. Fix: add descriptions clarifying the distinction or deprecate one.

## Issue 8: Eval Execution Naming Confusion (Medium)
Three similarly-named endpoints for running evals produce different results with no descriptions:
| **Path** | **Summary** |
|:-:|:-:|
| GET .../eval/{eval_id}/eval_config/{eval_config_id}/run_task_run_eval | Run Eval Config |
| GET .../eval/{eval_id}/run_eval_config_eval | Run Eval Config Eval |
| GET .../eval/{eval_id}/eval_config/{eval_config_id}/score_summary | Get Eval Config Score Summary |
| GET .../eval/{eval_id}/eval_configs_score_summary | Get Eval Configs Score Summary |
The difference between "Run Eval Config" and "Run Eval Config Eval" is completely opaque. Fix: add descriptions and consider renaming to clarify what each endpoint runs against (e.g., one runs against a specific run config, the other runs against all?).

## Issue 9: Missing Schema Descriptions (Medium)
172 of 263 schemas (65%) have no description, and 788 schema properties have no description. Priority schemas to document:
### Schemas with no description that are high-value for agents
AnswerOption
ApiPrompt
AppropriateToolUseProperties
AvailableModels
AvailableProviderInfo
BiasProperties
BuildPromptRequest / BuildPromptResponse
BulkCreateDocumentsResponse / BulkUploadResponse
ChunkerConfig / ChunkerType
CompletenessProperties
All *Properties schemas (e.g., AppropriateToolUseProperties, BiasProperties, CompletenessProperties) appear to be eval-related configuration objects. Without descriptions, an agent cannot understand what they configure or when to use each one.

## Issue 10:check_entitlements Description Contains Code Artifacts (Low)
The description for GET /api/check_entitlements includes raw Python docstring content: "Args:\n feat...". This is a documentation generation artifact and should be cleaned up into proper prose.

## Issue 11: No tags

P1: Come up with a tagging plan to sub-divide the APIs into a set of tabs. This allows better agentic usage.

## Recommended Fix Priority
| **Priority** | **Issues** |
|:-:|:-:|
| **P0 — Fix immediately** | Issue 6 (run vs runs confusion), Issue 5 (GET for mutations), Issue 7 (repair duplication) |
| **P1 — High impact** | Issue 1 (missing descriptions — focus on run, eval, copilot endpoints first), Issue 3 (path naming inconsistencies), Issue 4 (duplicate summaries) |
| **P2 — Important** | Issue 2 (parameter descriptions — at least all ID params), Issue 8 (eval execution naming), Issue 9 (key schema descriptions) |
| **P3 — Polish** | Issue 10, remaining schema property descriptions |

