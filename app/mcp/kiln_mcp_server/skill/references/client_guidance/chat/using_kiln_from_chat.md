---
name: using_kiln_from_chat
description: How a chat client works with Kiln and its user - the routing of a request to its mode, working with the user, keeping the user in the loop, links into the app, what this connection cannot do, how to read the words of Kiln Harness Tuner in the shared documents, and the files of this folder.
---

For chat clients working with a user. A non-interactive agent with its own instructions does not need this file.

# Using Kiln from a chat

Read this file at the start of a session, after `SKILL.md`. It holds the rules for working with the user and the routing of each request to its mode. `SKILL.md` lists the rest of the skill.

## Routing

Read the mode that fits the user's request before other skill files. A mode names the knowledge files and endpoint docs of its workflows.

| Mode | Read when the user wants to | Path |
|------|-----------------------------|------|
| Project Operations | Create a project or task; edit project resources (task instruction, prompts, run configs, evals); check project status; inspect one run and its output | `references/client_guidance/chat/project_operations.md` |
| Improve Task | Make an existing agent better: quality, cost, speed, model choice; read or compare eval scores; create an eval to fix a quality problem; improve a prompt from eval feedback; fine-tune; add a tool, a skill, retrieval or a sub-agent to a task | `references/client_guidance/chat/improve_task.md` |
| Learn About Kiln | Understand a feature ("what is X", "how does Y work"); fix an error or a provider problem; ask about Kiln the product | `references/client_guidance/chat/learn_about_kiln.md` |

- When the request is unclear, or fits more than one mode, read `references/client_guidance/chat/establish_intent.md`: it has the questions to ask and the routing examples.
- An eval or prompt change made *because* of a quality problem is Improve Task. Standalone setup ("set up evals for my new task") is Project Operations.
- When the user's goal changes, route again.

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

**Keep the user in the loop.** When you have made about five tool calls since your last message to the user, tell them in one or two sentences what you found and what you will do next, then go on.

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

## How to read the shared documents

The knowledge of `references/improving_agents/index.md` and
`references/levers/index.md`, and files such as
`references/knowledge/memory.md`, are shared with Kiln Harness Tuner,
whose agents run without a person and whose code does part of the work.
Their rules apply to you as written. Read them this way:

- A role of Kiln Harness Tuner (its planner, builder or analyzer) is you.
- An input of Kiln Harness Tuner that the user decides (`allowed_models`,
  the model policy, `measurement_prices`): ask the user. An input that
  Kiln Harness Tuner measures (`train_noise`, `train_detectability`,
  `probe_results`, `lever_attempts`): you do not have it, so follow the
  document's rule for when it is absent.
- "Code checks", "code refuses", "the code detection in your input":
  Kiln Harness Tuner's code does this for its agents. Check it yourself,
  with the same rule and threshold.
- An output field (`open_questions`, `rejected_summary`, `rationale`):
  tell the user.
- A record line that Kiln Harness Tuner writes, such as
  `— REJECTED AT VAL`: read it, and never write it
  (`references/knowledge/memory.md`).
- A Kiln Harness Tuner tool that Kiln does not have (the screening): tell
  the user it needs Kiln Harness Tuner. For the skill installer or the
  skill-authoring guide, create the skill with
  `references/knowledge/adding_skills.md`, which writes the `SKILL.md`
  body only, with no `references/` files.
- "The stop rules and the confirmation on val", in "A clear measurement
  outranks a document" of `references/improving_agents/index.md`: judge a
  result with
  `references/client_guidance/chat/running_an_experiment_from_chat.md`.

## The files of this folder

| File | Read it when |
|---|---|
| `references/client_guidance/chat/using_kiln_from_chat.md` | This file: at the start of a session |
| `references/client_guidance/chat/project_operations.md` | The mode Project Operations (see "Routing") |
| `references/client_guidance/chat/improve_task.md` | The mode Improve Task |
| `references/client_guidance/chat/learn_about_kiln.md` | The mode Learn About Kiln |
| `references/client_guidance/chat/establish_intent.md` | The request is unclear, or fits more than one mode |
| `references/client_guidance/chat/running_an_experiment_from_chat.md` | Before any experiment or comparison of run configs: when to recommend Kiln Harness Tuner, and how to measure a one-off change, judge it and keep it |
| `references/client_guidance/chat/freeform_help.md` | No knowledge file covers the request: the last resort |
