---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. This skill says how to work with the user's running Kiln app through its API - projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills and RAG - and how to make an agent better. Use when the user asks for /kiln or wants to work with Kiln.
---

# Kiln

This is the Kiln skill. The Kiln app serves it over MCP, through the `kiln_skill` tool. It holds what an agent needs to work with Kiln: its concepts and features, how to make an agent better, the project's memory, and the reference for the Kiln API. Its rules apply while you do Kiln work; they do not change how you handle anything else.

## Reading this skill

- Read any path in this skill by calling `kiln_skill` with that exact path as `path`, for example `kiln_skill(path="references/knowledge/specs_and_evals.md")`.
- Do not guess a file name: each file is named by this text or by a file it leads to.
- This text arrived through a `kiln_skill` call and can drop out of the conversation, for example when it is summarised. When it is no longer in the conversation, read it again. The same holds for any skill file that your current work depends on.

## Who reads this skill

Different kinds of client read this skill. Most files serve every client; use the files meant for you.

- **A chat client**, an agent working with a user (Claude Code, Claude Desktop, Codex, OpenCode and others): at the start of every session, read `references/client_guidance/chat/using_kiln_from_chat.md`. It says how to work with the user, how to link to the Kiln UI, and which mode fits each request.
- **A non-interactive agent with its own instructions** (such as Kiln Harness Tuner): your instructions name the files you need. Where a skill file and your instructions disagree, your instructions win. Ignore any instruction in a skill file to ask the user. Do not read `references/client_guidance/chat/`; if you read a file there, fit any lesson to your own process.
- **Kiln Harness Tuner with eval building turned on** (experimental, off by default): `references/client_guidance/harness_tuner/eval_building.md`. Every other client never reads or follows it.

## Kiln concepts

- **Kiln** is an app for building, evaluating and optimizing AI agents. The user runs it on their own computer, and you reach it over MCP.
- **Projects and tasks.** A project holds one or more tasks. A task is one AI agent: its instruction, its input and output schemas, and whether it is single-turn or multi-turn. Most work is on one task: `references/knowledge/create_task.md`.
- **Run configs.** A run config is one way to run a task: the model and its AI provider, the prompt, the run parameters (such as temperature), the output mode, and the tools and skills the agent may call. To compare agents is to compare run configs. Creating one: `references/knowledge/model_create_configs.md`.
- **Models and AI providers.** Kiln runs models from many AI providers (OpenAI, Anthropic, OpenRouter, Ollama and others). The user connects each AI provider with its key. Choosing a model, its price and its capabilities: `references/knowledge/model_work.md`. Connecting an AI provider: `references/knowledge/provider_setup.md`. Local and private models: `references/knowledge/local_private_on_prem.md`.
- **The dataset.** Every run of a task, with its ratings and tags: `references/docs/organizing-datasets.md`.
- **The Kiln UI.** Kiln has a web UI at `http://localhost:8757`. Chat clients link the user to its pages as `references/client_guidance/chat/using_kiln_from_chat.md` says.

## Kiln features

- **Evals and specs.** A spec states one behaviour the agent must have; an eval measures it with a judge. What they are and the Eval Builder: `references/knowledge/specs_and_evals.md`. Creating one: `references/knowledge/create_eval.md`. The judges: `references/knowledge/judge_types.md`. Reading scores: `references/knowledge/eval_scores.md`. Benchmark evals from reference data and synthetic-user drives: `references/knowledge/benchmark_eval_inputs.md`. An eval's items are split into train, val and test: `references/knowledge/train_val_test.md`.
- **Prompts.** Saved prompts, prompt generators and prompts with examples: `references/knowledge/prompt_rewrite.md`. A review checklist: `references/knowledge/prompt_audit.md`.
- **Synthetic data.** Kiln generates inputs and outputs for evals and fine-tuning, in the app, and an agent never makes eval data: `references/knowledge/synthetic_data.md`. The Data Guide that shapes the inputs: `references/knowledge/data_guides.md`.
- **Fine-tuning.** Training a custom model on the task's data: `references/knowledge/fine_tuning.md`.
- **Tools.** MCP tool servers, local or remote, that a run config can call: `references/knowledge/tools.md`. Code tools, Python functions as tools (Beta, needs code trust): `references/knowledge/code_tools.md`.
- **Sub-agents.** A Kiln task that another task calls as a tool: `references/knowledge/subagents.md`.
- **Skills.** Instructions an agent loads when it needs them: `references/knowledge/adding_skills.md`.
- **Documents and search (RAG).** A document library, and search tools over it: `references/knowledge/rag.md`.
- **Issues.** An issue tracker that keeps the data to reproduce, evaluate and fix an AI system's problems: `references/docs/issues.md`.
- **Memory.** Lasting knowledge about a project: what was tried, learned and decided (below).

## Skill contents

Use these to find the rest of this skill.

### Help and the project's state

- `references/knowledge/app_help.md` — Kiln errors, AI provider problems, and "how do I…" questions. It names the file for each topic.
- `references/knowledge/project_status.md` — the current state of a project and task, and one run.
- `references/knowledge/working_with_project_files.md` — the project's files on disk: read them when that is faster than the API; write only through the API.
- `references/docs/docs_index.md` — Kiln's help articles, each with its public URL. They rank below the knowledge files: when both cover a topic, trust the knowledge file, and use the article as a link for further reading.

### Improving agents

- A **lever** is one part of an agent that a change can touch (the prompt, the model, run parameters, the output mode, tools, skills, a new tool), and how to change it: `references/levers/index.md`.
- A **smell** is an issue in the design of an agent. A **playbook** is an ordered list of things to try for one problem or goal. A **technique** is one optimisation. A smell or a playbook leads to techniques, and a technique names the levers it uses. Start from `references/improving_agents/index.md`.
- `references/knowledge/diagnose_an_agent.md` — the calls that read an agent, its scores on train and its failing train items, before you choose what to change.
- `references/knowledge/train_val_test.md` — the split rule, which call reads which split, and the leak rules. Read it before you measure or compare run configs.
- `references/knowledge/experiment_costing.md` — the full cost of an experiment, lane by lane, measured before you spend. Read it before you run or propose an eval run, a sweep or a round of candidates.
- `references/knowledge/code_tool_authoring.md` — writing a code tool or a wrapper for an agent as an experiment, with eight wrapper templates.

### Memory

`references/knowledge/memory.md` — the project's durable memory: what to read at the start of Kiln work, what you may record, and the formats of the records that Kiln Harness Tuner's code writes. Read it before you read or write a memory.

### The Kiln API

If you have the `call_kiln_api` tool, read `references/knowledge/api_docs/calling_the_kiln_api.md` before your first call: the rules for every call. `references/knowledge/api_docs/api_index.md` lists the catalogues of endpoints, and each catalogue row names the endpoint doc to read before you call it.

### Other

- `references/knowledge/typesafe_jev.md` — TypeSafe AI (Jev), a classification-only AI provider for judges and closed-set tasks.

## Chat client guidance

For chat clients only: read `references/client_guidance/chat/using_kiln_from_chat.md` at the start of every session. It lists the other chat files. A non-interactive agent with its own instructions skips it.
