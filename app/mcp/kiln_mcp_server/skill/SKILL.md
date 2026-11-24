---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. This skill says how to work with the user's running Kiln app through its API - projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills and RAG - and how to make an agent better. Use when the user asks for /kiln or wants to work with Kiln.
---

# Kiln

Kiln is an app for building, evaluating and optimizing AI agents: projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills and RAG. The user runs Kiln on their own computer, and you reach it through the `call_kiln_api` tool, which calls Kiln's REST API. The rules in this file apply while you do Kiln work; they do not change how you handle anything else.

## Reading skill files

- Every path in this skill is relative to the skill root (the folder of this file), for example `references/knowledge/specs_and_evals.md`. A path is never relative to the file that names it.
- To read a file, give its path to the tool that returned this text, exactly as written here.
- Only the paths that this skill writes exist. Do not guess a file name; when you cannot find the file you need, read the mode or catalogue that lists it.
- This text arrived through a tool call and can drop out of the conversation, for example when old context is summarised. When it is no longer in the conversation, read it again before more Kiln work. The same holds for a mode, knowledge file or endpoint doc that your current work depends on.

## Routing

Read the mode that fits the user's request before other skill files. A mode names the knowledge files and endpoint docs of its workflows.

| Mode | Read when the user wants to | Path |
|------|-----------------------------|------|
| Project Operations | Create a project or task; edit project resources (task instruction, prompts, run configs, evals); check project status; inspect one run and its output | `references/modes/project_operations.md` |
| Improve Task | Make an existing agent better: quality, cost, speed, model choice; read or compare eval scores; create an eval to fix a quality problem; improve a prompt from eval feedback; fine-tune; add a tool, a skill, retrieval or a sub-agent to a task | `references/modes/improve_task.md` |
| Learn About Kiln | Understand a feature ("what is X", "how does Y work"); fix an error or a provider problem; ask about Kiln the product | `references/modes/learn_about_kiln.md` |

- When the request is unclear, or fits more than one mode, read `references/modes/establish_intent.md`: it has the questions to ask and the routing examples.
- An eval or prompt change made *because* of a quality problem is Improve Task. Standalone setup ("set up evals for my new task") is Project Operations.
- When the user's goal changes, route again.

## Calling the Kiln API

`call_kiln_api` takes `method`, `url_path`, and optionally `body`, `query_params`, `jq_filter`, `body_limit` and `save_to_tmpfile`.

- **Read the endpoint doc before your first call to an endpoint.** The docs are in `references/knowledge/api_docs/`. Each knowledge file lists the docs of its workflows. To find another endpoint, start from `references/knowledge/api_docs/api_index.md`: it lists one catalogue per area of the API, and each catalogue names the doc of each endpoint. When no catalogue lists a path, the endpoint does not exist; say so instead of guessing. Never guess a request body, a response field or a path.
- **A non-2xx answer is data.** A result with a `status_code` of 400 or more is the API's own error. Read the body and act on it; it is not a failure of the tool.
- **Narrow large answers.** Use `jq_filter` to take only the fields you need, use the paging and filter parameters of the endpoint, or set `save_to_tmpfile` to get a file path in place of the body. List before detail: pull the IDs and names first, then drill into one item.
- **Query parameters go in `query_params`**, never as `?key=value` in `url_path`: `call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/runs", query_params={"page_size": "50"})`. App links in your reply still use `?` normally.
- **An event stream that ends does not mean the work succeeded.** A streaming endpoint returns when its stream ends. Then read the status of the job or the resource, and its errors.
- **Writing `jq_filter`:** quote the 200 response shape of the endpoint doc before you write the filter (`array of X` → `.[] | {fields}`; a named wrapper such as `items` → `.items[]`). The filter is raw jq inside a JSON string: no shell quotes, and no quotes around field paths. A literal-string result, an echo of the filter, `Cannot index array with string`, or null on a field you expected means the filter or the shape is wrong: read the endpoint doc again and name the line that gives the field path before you retry. The same entity can have different field paths on different endpoints.
- **Reuse what you have.** A response already in the conversation stays valid until something changed it. Call again only when the data may have changed (a write since, an error, or the user asks about the current state).
- **Rate limits.** A provider `429` or "rate limit exceeded" is a transient error and a signal to slow down. Run fewer calls at once and retry. It is never a reason to switch the model or the provider: the user may be held to one provider, and a switch changes what you measure.
- **Keep the user in the loop.** When you have made about five tool calls since your last message to the user, tell them in one or two sentences what you found and what you will do next, then go on.

## Working with the user

Ask the user before an operation that is destructive or that cannot be undone, unless they asked for exactly that operation: a DELETE, an overwrite of the user's prompt text or task instruction, and anything that removes data. When the user's message asks for a change ("update X", "apply this rewrite"), the ask is the consent: make the change and report it.

Two operations let code run on the machine where Kiln runs, with no sandbox. Always involve the user first, even when they asked for the result:

- **Code trust** (for a code tool or a code eval). Only the user can grant it. Read the state with `GET /api/projects/{project_id}/add_code_trust`. When the project is not trusted, tell the user what the code will run and that it runs with no sandbox, give them the link `http://localhost:8757/settings/trust_code/{project_id}`, and ask them to tell you when they have approved. Then read the state again, and go on only when it is trusted. Trust lasts until Kiln restarts.
- **Adding a local MCP server.** Say what will run and that it runs with no sandbox, and add it only when the user agrees.

A knowledge file can name other operations to ask about first; follow it.

Everything else that has an endpoint, do it and report the result; do not hand the user a plan to click through.

How to reply:

- **Lead with the recommendation.** Open with the concrete next step, then the evidence, then the data, then the links. A trailing question is not a recommendation.
- **Be concise.** Give the shortest answer that delivers it, unless the user asks for detail.
- **Match the user's scope.** A question about one run config does not need a scan of all of them. Check completion before you report scores: an eval at 0% completion has no scores.
- **Admit uncertainty.** When no skill file or API response says it, say "I'm not sure" rather than make it up.

## Links into the app

The Kiln app runs at `http://localhost:8757`. Write every link to an app page as `http://localhost:8757/<path>`, as a Markdown link: `[Run configs](http://localhost:8757/optimize/{project_id}/{task_id})`. Replace `{project_id}`, `{task_id}` and the other placeholders with real IDs. Never write a bare app path, and never another host: `https://kiln.tech` is Kiln's website, not the app. When no page fits, give no link; never invent a path.

Every table, result and created resource gets a link, so the user can follow along. The main pages:

| Page | Link |
|------|------|
| Run | `http://localhost:8757/run` |
| Dataset | `http://localhost:8757/dataset/{project_id}/{task_id}` |
| Specs and evals | `http://localhost:8757/specs/{project_id}/{task_id}` |
| Optimize (run configs) | `http://localhost:8757/optimize/{project_id}/{task_id}` |
| Prompts | `http://localhost:8757/prompts/{project_id}/{task_id}` |
| Models | `http://localhost:8757/models` |
| Tools | `http://localhost:8757/tools/{project_id}` |
| Skills | `http://localhost:8757/skills/{project_id}` |
| Documents and search | `http://localhost:8757/docs/{project_id}` |
| Fine-tune | `http://localhost:8757/fine_tune/{project_id}/{task_id}` |
| Synthetic data | `http://localhost:8757/generate/{project_id}/{task_id}` |
| Background jobs | `http://localhost:8757/jobs` |
| Settings | `http://localhost:8757/settings` |

More pages, for one run config, one run or one task:

| Page | Link |
|------|------|
| Create a run config | `http://localhost:8757/optimize/{project_id}/{task_id}/run_config/create` |
| One run config | `http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{run_config_id}` |
| Run page with a run config selected | `http://localhost:8757/run?run_config_id={run_config_id}` |
| Run page with a tool selected | `http://localhost:8757/run?tool_id={tool_id}` |
| One run and its output | `http://localhost:8757/dataset/{project_id}/{task_id}/{run_id}/run` |
| Task settings | `http://localhost:8757/settings/edit_task/{project_id}/{task_id}` |

The knowledge files list the pages of their own areas.

## Other entry points

- `references/docs/docs_index.md` — Kiln's help articles, each with its public URL. Read it for "how do I…" questions and to point the user at the docs.
- `references/levers/index.md` — the parts of a Kiln agent that an experiment can change (prompt, model, run parameters, output mode, tools, skills, a new tool), and how to change each one.
- `references/improving_agents/index.md` — what to try to make an agent better: the smells, the playbooks and the techniques, and how to read them.
- `references/knowledge/run_an_experiment.md` — how to measure a change to an agent, judge it and keep it, and when to recommend Kiln Harness Tuner in place of a one-off. Read it before any experiment or comparison of run configs.
- `references/knowledge/train_val_test.md` — the split rule for improving an agent, which call reads which split, and the leak rules. Read it before you measure or compare run configs.
- `references/knowledge/memory.md` — the project's durable memory: what to read at the start of Kiln work, what you may record, and the formats that Kiln Harness Tuner writes. Read it before you read or write a memory.
- `references/knowledge/working_with_project_files.md` — the project's files on disk: read them when that is faster than the API; write only through the API; never change a prompt, skill or run config in place.
- `references/knowledge/model_work.md` — models: which to choose, their prices, providers and capabilities, through the model info endpoints.

## What you cannot do over this connection

Some capabilities have no endpoint here, on purpose: they hold credentials, open files or folders on the user's computer, or change settings that only the user should change. For each, ask the user to do it in the app, and give the link:

| Capability | Ask the user to do it at |
|------------|--------------------------|
| Connect or disconnect a provider API key; add or remove an OpenAI-compatible provider | `http://localhost:8757/settings/providers` |
| Sign in to Kiln Pro, or fix an invalid Kiln Pro key | `http://localhost:8757/settings/providers/kiln_pro` |
| Set up git sync for a project, import a project from a git repository, or import a local project with the file picker | `http://localhost:8757/settings/import_project` |
| Read, change or remove a project's git sync settings | `http://localhost:8757/settings/edit_project/{project_id}` |
| Change a setting that has no endpoint of its own; open the application logs (the row "Application Logs") | `http://localhost:8757/settings` |
| Open a project's folder | `http://localhost:8757/settings/manage_projects` |
| Open a document's folder, or download the original document | `http://localhost:8757/docs/library/{project_id}/{document_id}` |
| Open a skill's folder | `http://localhost:8757/skills/{project_id}/{skill_id}` |
| Grant code trust to a project, for a code tool or a code eval ("Working with the user" says how to ask) | `http://localhost:8757/settings/trust_code/{project_id}` |

Two errors mean the user must connect something first:

- **Kiln Pro is not connected, or its key is not valid.** Tell the user which function needs Kiln Pro, ask them to sign in at `http://localhost:8757/settings/providers/kiln_pro`, then try again.
- **No provider is connected for the model** (the model info endpoints show the status `not_connected`). Name the provider and ask the user to connect it at `http://localhost:8757/settings/providers`, or offer a model whose status is `ready`.
