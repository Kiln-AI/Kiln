---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. This skill says how to work with the user's running Kiln app through its API - projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills and RAG - and how to make an agent better. Use when the user asks for /kiln or wants to work with Kiln.
---

# Kiln

This is the Kiln skill: an agent-skill-shaped tool for Kiln, served over MCP. Kiln is an app for building, evaluating and optimizing AI agents: projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills and RAG. The user runs Kiln on their own computer. The rules in this skill apply while you do Kiln work; they do not change how you handle anything else.

## Reading skill files

- Every path in this skill is relative to the skill root (the folder of this file), for example `references/knowledge/specs_and_evals.md`. A path is never relative to the file that names it.
- To read a file, give its path to the tool that returned this text, exactly as written here.
- The tool cannot list a folder. Every file is reached by a path that some file names, starting from the parts below. Do not guess a file name.
- This text arrived through a tool call and can drop out of the conversation, for example when old context is summarised. When it is no longer in the conversation, read it again before more Kiln work. The same holds for any skill file that your current work depends on.

## Who reads this skill

Different kinds of client read this skill. Most files serve every client; use the files meant for you.

- **A chat client**, an agent working with a user (Claude Code, Claude Desktop, Codex, OpenCode and others): at the start of every session, read `references/client_guidance/chat/using_kiln_from_chat.md`. It says how to work with the user and which mode fits each request.
- **A non-interactive agent with its own instructions** (such as Kiln Harness Tuner): your instructions name the files you need. Where a skill file and your instructions disagree, your instructions win. Ignore any instruction in a skill file to ask the user. Do not read `references/client_guidance/chat/`; if you read a file there, fit any lesson to your own process.

## The parts of the skill

### Kiln's features

Each feature has a knowledge file: how it works in Kiln, its endpoints, its traps and its app pages. Read it before you work on the feature or answer a question about it.

| Feature | What it provides | File |
|---|---|---|
| App Help | Starting point for all "what is X" and "how does Y work" feature questions (Eval Builder, evals, RAG, tools) — load this file first; it delegates to the right sub-file. Also covers troubleshooting Kiln errors, provider issues, and "how do I..." questions | `references/knowledge/app_help.md` |
| Provider Setup | Provider/API key help — connecting/disconnecting providers, reading current connectivity state, distinguishing configured-for-this-task vs connected-to-workspace, troubleshooting | `references/knowledge/provider_setup.md` |
| Project Status | The current state of a project and task — run configs, eval scores, specs, prompts, providers; inspecting one run | `references/knowledge/project_status.md` |
| Create Task | A new task from scratch — requirements, the prompt, single-turn or multi-turn, the first run config and specs, driving a multi-turn conversation | `references/knowledge/create_task.md` |
| Project Files | The project's files on disk — read directly when faster, write only through the API, never change a prompt, skill or run config in place | `references/knowledge/working_with_project_files.md` |
| Model Work | Model tiers, pricing, capabilities, gap analysis, provider reference — canonical home for model questions | `references/knowledge/model_work.md` |
| Run Configs | Creating a run config, model parameters, name rules | `references/knowledge/model_create_configs.md` |
| Prompts | Reading prompts, saved prompts and the run config that uses one, building prompts with examples, the prompt types | `references/knowledge/prompt_rewrite.md` |
| Prompt Audit | A review checklist for a prompt | `references/knowledge/prompt_audit.md` |
| Fine-Tuning | When to fine-tune, the job workflow, datasets, the check before submitting, status | `references/knowledge/fine_tuning.md` |
| Local and Private Models | Open-weight models for privacy, local or on-prem use | `references/knowledge/local_private_on_prem.md` |
| Evals | What evals are, eval pipeline, Eval Builder vs manual, agent's role | `references/knowledge/specs_and_evals.md` |
| Create Eval | Eval types, the Eval Builder links, the map from a problem to a type of eval | `references/knowledge/create_spec.md` |
| Judge Types | The eval judge menu — LLM judge, deterministic checks, code evals; what each is and when to use it | `references/knowledge/judge_types.md` |
| TypeSafe AI (Jev) | Classification-only provider for judges and closed-set structured tasks — where it fits, what it rejects, judge tips, reading its probabilities | `references/knowledge/typesafe_jev.md` |
| Eval Scores | Score reading, scorecards, comparison patterns | `references/knowledge/eval_scores.md` |
| Benchmark Evals | Evals built on eval inputs with reference data, synthetic-user drives, benchmarking a run config | `references/knowledge/benchmark_eval_inputs.md` |
| Data Guides | Data Guides for synthetic data — what they are, manual vs Kiln Pro authoring | `references/knowledge/data_guides.md` |
| Diagnose an Agent | The calls that read an agent, its scores on train and its failing train items, before you choose what to change | `references/knowledge/diagnose_an_agent.md` |
| RAG | Document retrieval — what it is, how to set up | `references/knowledge/rag.md` |
| Tools | MCP tool servers — what they are, how to configure | `references/knowledge/tools.md` |
| Code Tools | Native Python functions registered as tools (Beta, trust-gated) — what they are, how they differ from code evals | `references/knowledge/code_tools.md` |
| Code Tool Authoring | Writing a code tool or a wrapper for an agent as an experiment, with eight wrapper templates | `references/knowledge/code_tool_authoring.md` |
| Skills | Project skills — creating, editing, the name limits, attaching one to a run config | `references/knowledge/adding_skills.md` |
| Sub-Agents | Kiln Task as Tool — sub-agent vocabulary mapping, 5-step setup workflow, tool name/description guidance | `references/knowledge/subagents.md` |

Kiln's help articles, each with its public URL, are listed in `references/docs/docs_index.md`. They rank below the knowledge files: when both cover a topic, trust the knowledge file, and use the article as a link for further reading.

### Improving agents

- A **lever** is one part of an agent that a change can touch (the prompt, the model, run parameters, the output mode, tools, skills, a new tool), and how to change it: `references/levers/index.md`.
- A **smell** is an issue in the design of an agent. A **playbook** is an ordered list of things to try for one problem or goal. A **technique** is one optimisation. A smell or a playbook leads to techniques, and a technique names the levers it uses. Start from `references/improving_agents/index.md`.
- `references/knowledge/train_val_test.md` — the split rule, which call reads which split, and the leak rules. Read it before you measure or compare run configs.
- `references/knowledge/experiment_costing.md` — the full cost of an experiment, lane by lane, measured before you spend. Read it before you run or propose an eval run, a sweep or a round of candidates.

### Memory

`references/knowledge/memory.md` — the project's durable memory: what to read at the start of Kiln work, what you may record, and the formats of the records that Kiln Harness Tuner's code writes. Read it before you read or write a memory.

### The Kiln API

If you have the `call_kiln_api` tool, read `references/knowledge/api_docs/calling_the_kiln_api.md` before your first call: the rules for every call. `references/knowledge/api_docs/api_index.md` lists the catalogues of endpoints, and each catalogue row names the endpoint doc to read before you call it.

### Chat client guidance

For chat clients only: `references/client_guidance/chat/using_kiln_from_chat.md`, read at the start of every session, and the files it lists. A non-interactive agent with its own instructions skips it.
