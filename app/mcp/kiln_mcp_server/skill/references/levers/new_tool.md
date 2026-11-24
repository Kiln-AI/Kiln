---
title: Code tools
description: Python code tools for the subject task - a new tool, a clone of a code tool with a new description, or a wrapper of any attached tool.
reviewed: 2026-11-13
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_code_tools.md
  - references/knowledge/api_docs/get_api_projects_project_id_code_tools_code_tool_id.md
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md
  - references/knowledge/api_docs/get_api_projects_project_id_add_code_trust.md
  - references/knowledge/api_docs/post_api_projects_project_id_test_code_tool.md
  - references/knowledge/api_docs/post_api_projects_project_id_code_tools.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/post_api_projects_project_id_code_tools_code_tool_id_archive.md
---

# Code tools

## What it is

A code tool is a Python function that the subject model can call. Kiln runs
it with no sandbox (`references/knowledge/code_tools.md`). It can call other
tools through its `tool_allowlist`. The model sees its `tool_function_name`,
its `tool_description` and the descriptions in its `parameters_schema`.

This lever covers three kinds of change:

- **A new tool**: code with no nested call, or code that calls the
  subject's tools.
- **A clone with a new description**: the code of an existing code tool,
  with a new `tool_description` or new parameter descriptions.
- **A wrapper**: a code tool that calls an attached tool of any kind (a
  code tool, an MCP tool, a built-in tool) and changes what goes in or what
  comes back. An MCP or built-in tool gets a new description only through a
  wrapper.

The subject's own tools are the company's software. You do not
change them. You add code tools beside them.

## How to change it

1. Read the trust state with
   `references/knowledge/api_docs/get_api_projects_project_id_add_code_trust.md`.
   Trust is granted once per project and app session, and only the user can
   grant it. The code runs on the machine where Kiln runs, with no sandbox.
   `references/knowledge/code_tools.md` says how to ask the user. An
   untrusted create or dry run answers `not_trusted: true` and does nothing.
2. Read the source:
   `references/knowledge/api_docs/get_api_projects_project_id_code_tools_code_tool_id.md`
   for a code tool to clone, or
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md`
   for the parameters of the tool to wrap.
3. Dry-run the code:
   `references/knowledge/api_docs/post_api_projects_project_id_test_code_tool.md`.
   Nested calls run for real, so a dry run uses reads only, or an id that
   does not exist.
4. Create the tool:
   `references/knowledge/api_docs/post_api_projects_project_id_code_tools.md`.
   The result gives its id.
5. Create a new run config with
   `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`,
   with `kiln_tool::code::<new_id>` in `tools_config.tools`. When the new
   tool replaces a tool, drop the old id on the same run config.

Rules of the object:

- **The functional fields are fixed when the tool is created.** A change
  is a new tool. Never change or archive a tool that another run config
  uses.
- **Each tool has a fresh `tool_function_name`.** Kiln refuses a run
  config, or an allowlist, in which two tools share one.
- **A subject tool allowlists only subject tools.** Never a tool that can
  reach the Kiln server, never a memory tool, never a skill id, never the
  tool's own id. `references/knowledge/code_tool_authoring.md` gives the
  rule in full.
- `references/knowledge/api_docs/post_api_projects_project_id_code_tools_code_tool_id_archive.md`
  is for a tool that this build created and that no run config uses.

## Limits

- The code has at most 64 KB. The parameter names of `run(...)` match
  `parameters_schema`.
- `timeout_seconds` is shared by all nested calls of one call. Nested calls
  go at most 10 deep.
- A nested result can arrive parsed, or as a JSON string. The code parses
  both.
- No value from a train item goes into the code or the description (the
  leak rules of `references/knowledge/train_val_test.md`). Code searches
  each build for copies of train content and of eval text.
- The tool's description moves with the tool. A run config that drops the
  tool drops its description too.
- When the parent's output mode sends the schema as a tool
  (`function_calling`, `function_calling_weak`, or `default` outside Ollama
  and Docker Model Runner), Kiln refuses every call once a tool or a skill
  is attached. Set the mode on the same run config by the fallback of
  [model](references/levers/model.md), step 4, and list it in `change`. The lever
  [output_mode](references/levers/output_mode.md) gives the modes.

## See also

- `references/knowledge/code_tools.md`: code tools in Kiln, code trust,
  and the create, test and attach calls.
- `references/knowledge/code_tool_authoring.md`: the contract, the
  allowlist rule, the build rules, a worked example, and eight wrapper
  templates, one for each mechanical failure.
- In a chat with a user:
  `references/client_guidance/chat/running_an_experiment_from_chat.md`.
