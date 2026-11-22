---
title: The attached tools
description: Which existing tools a run config attaches - code, MCP, built-in, Kiln task and RAG tools - attached or dropped on a new run config, with no new code.
reviewed: 2026-11-13
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/get_api_projects_project_id_available_tools.md
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md
  - references/knowledge/api_docs/get_api_projects_project_id_code_tools.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
---

# The attached tools

## What it is

A run config attaches tools in `tools_config.tools`, a list of tool ids. The
model sees the name, the description and the parameters of each attached
tool in every call. This lever is the list itself: which of the tools that
already exist the agent gets. It adds no tool and changes no tool.

The tool id forms:

- `kiln_tool::code::<code_tool_id>`: a code tool of the project.
- `mcp::local::<server_id>::<tool_name>` and
  `mcp::remote::<server_id>::<tool_name>`: a tool of a connected MCP server.
- `kiln_task::<tool_server_id>`: another Kiln task, called as a tool.
- `kiln_tool::rag::<rag_config_id>`: the search tool of a RAG config.
- Built-in tools, with the `kiln_tool::` prefix.

A skill is attached in the same list, as `kiln_tool::skill::<skill_id>`. A
skill is the lever [skill](references/levers/skill.md), not this one.

## How to change it

1. Read the parent's list:
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`
   gives `tools_config.tools`.
2. Read what can be attached:
   `references/knowledge/api_docs/get_api_projects_project_id_available_tools.md`
   gives each tool set with its `type`, and each tool with its id, name and
   `function_name`.
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md`
   gives the description and the parameters that the model sees.
   `references/knowledge/api_docs/get_api_projects_project_id_code_tools.md`
   gives the project's code tools.
3. Create a new run config with
   `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`.
   Copy every property of the parent, and set the changed
   `tools_config.tools`.

Rules of the object:

- **The properties of a run config are fixed when it is created.** A new
  list is a new run config.
- **A new description is not this lever.** The description of an attached
  tool cannot change on the run config. A new description is a new tool: a
  clone of a code tool, or a wrapper of any tool. That is the lever
  [new_tool](references/levers/new_tool.md).
- **Two tools with one job on one run config** give the model a choice.
  When a new tool replaces an old one, the old id is dropped on the same
  run config.

## Limits

- This lever attaches only what exists. It does not connect an MCP
  server, and it does not create a RAG config or a Kiln task tool.
- When a dropped tool is still named in the prompt or in an attached
  skill, the text points at nothing. After the build, search the text for
  the name yourself and change each mention.
- A code tool can call a tool that it lists in its `tool_allowlist` when
  that tool is not attached. To drop a tool from the model's view does not
  remove it from a wrapper.
- Never attach a tool that can reach the Kiln server to the subject task.
  It gives the subject model a channel into the Kiln API.
- When the parent's output mode sends the schema as a tool
  (`function_calling`, `function_calling_weak`, or `default` outside Ollama
  and Docker Model Runner), Kiln refuses every call once a tool or a skill
  is attached. Set the mode on the same run config by the fallback of
  [model](references/levers/model.md), step 4, and record it as part of the change. The lever
  [output_mode](references/levers/output_mode.md) gives the modes.

## See also

- `references/knowledge/tools.md`: the tool types of Kiln, how to connect
  and attach them, and the tool id forms.
- `references/knowledge/subagents.md`: a Kiln task called as a tool.
- `references/knowledge/rag.md`: the search tool of a RAG config.
- `references/knowledge/run_an_experiment.md`: how to measure the change,
  judge it and keep it.
