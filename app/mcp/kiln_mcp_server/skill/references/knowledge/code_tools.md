---
name: code_tools
description: |
  Code tools — native Python functions registered as tools a task/agent can call at runtime (Beta, trust-gated). Distinct from code evals. Load when the user asks about code tools, "write a Python tool for my agent", or how to add a custom tool without an MCP server. Covers code trust, testing the code yourself, the dry run, create, attach and iterate through the API.
---
# Knowledge: Code Tools

A **code tool** is a Python function the user registers as a tool their task can call **at runtime** — a code alternative to wiring an external MCP server for a small piece of custom logic (parse something, do a calculation, hit an internal helper). New in this Kiln release, **Beta**.

Don't confuse it with a **code eval** (`references/knowledge/judge_types.md`): a code eval *scores* a run after the fact with a `score()` function; a code tool *runs during* the task as something the model can call. Both are user-authored Python in the same sandbox and share the same trust gate.

**You draft, test, create and attach code tools through the API**, with the user. The user can also do this in the app's tool settings (deep links below). A code tool that you build as an experiment on an agent (a new tool, or a wrapper of one of its tools) follows `references/knowledge/code_tool_authoring.md` and the lever `references/levers/new_tool.md` as well as this file.

## The essentials

- **Code trust comes first, and only from the user.** User-authored Python runs with no resource sandbox (network + filesystem are open, only crash isolation + a timeout), so the project needs **code trust** before a code tool runs; trust is per project, per app session. **Never present code from anywhere but the user's own session as trustworthy.**
- **The function is the tool.** The code defines a module-level `run(...)`; its parameter names match the tool's `parameters_schema`. The `tool_function_name` and `tool_description` are what the model reads to decide when to call it, and the schema's parameters are the tool's arguments. Results must be JSON-serializable (they reach the model as text).
- **Same import rules as code evals:** no import restrictions, but only what ships in the Kiln app's bundled Python is importable and there is no `pip install` at runtime — stdlib plus the common bundled libraries (`pydantic`, `httpx`, `requests`, `numpy`, `scipy`, `pandas`, `bs4`, `jinja2`, `yaml`, `PIL`, `jsonschema`, `regex`, …). Not bundled: `sklearn`, `lxml`, `rapidfuzz`, `polars`, `matplotlib`. When in doubt, prefer stdlib.
- **The code is fixed once created.** `PATCH .../code_tools/{code_tool_id}` changes the name and description only. A new version of the code is a new code tool.

## Drafting a code tool

**Drafting the Python is IN scope** — code destined for a Kiln artifact (a code tool or a code eval) is Kiln-feature work, not generic coding. **Always caveat the draft:** the user should read the logic and confirm it does what they intend. Don't present a draft as known-correct.

## Workflow: trust, test, create, attach, iterate

Read `references/knowledge/api_docs/code_tools_api_list.md` and the doc of each endpoint before you call it.

1. **Read the trust state** with `GET /api/projects/{project_id}/add_code_trust` (`references/knowledge/api_docs/get_api_projects_project_id_add_code_trust.md`). When the project is not trusted, **ask the user first**: say that the code will run on the machine where Kiln runs, with no sandbox. Grant trust with `POST /api/projects/{project_id}/add_code_trust` (`references/knowledge/api_docs/post_api_projects_project_id_add_code_trust.md`) only when they agree. Untrusted, a dry run or a create answers `not_trusted: true` and runs or saves nothing.
2. **Draft the code** with the user, as above.
3. **Run its tests yourself.** You can usually run Python where you work. Save the draft as a file, write a few tests of `run(...)` on the inputs the user expects and on bad inputs, and run them. When the code calls other tools (`from kiln import tools`), give the tests a stub of `kiln.tools` that returns the envelope those tools return. This tests the logic for free and does not touch Kiln. Say that your machine's Python may differ from the app's bundled one (the import rules above).
4. **Dry-run it in Kiln** with `POST /api/projects/{project_id}/test_code_tool` (`references/knowledge/api_docs/post_api_projects_project_id_test_code_tool.md`): the create fields plus `params`, the arguments of one call. It runs in the app's Python and saves nothing. Read `result`, `error`, `traceback`, `stdout` and `stderr`, and for nested calls `tool_call_log`. Nested calls run FOR REAL: dry-run with reads, or an id that does not exist, never a write.
5. **Create it** with `POST /api/projects/{project_id}/code_tools` (`references/knowledge/api_docs/post_api_projects_project_id_code_tools.md`). Its id is `kiln_tool::code::<code_tool_id>`.
6. **Attach it** to a run config: list its tool id in `tools_config.tools` of a new run config (`references/knowledge/model_create_configs.md`). The tools of a run config cannot be changed after creation (PATCH changes only its name, starred flag and prompt name).
7. **Iterate.** To change the code, go back to step 3 and create a new code tool, then a new run config with the new id. Archive the old tool (`POST .../code_tools/{code_tool_id}/archive`) only when no run config uses it (`references/levers/new_tool.md`). Function names may repeat across the project, but Kiln refuses a run config, or an allowlist, in which two tools share a `tool_function_name`: a new version that sits beside the old tool on one run config needs a new name.
8. **Report** the code tool ID and the link to the tools page.

## Deep links

| Action | Link |
|--------|------|
| Add / manage tools (the user can create a code tool here) | `http://localhost:8757/tools/{project_id}/add_tools` |
| Manage existing tools | `http://localhost:8757/tools/{project_id}` |

(For wiring an external tool server instead of a code tool, see `references/knowledge/tools.md`; for a sub-agent as a tool, `references/knowledge/subagents.md`.)

## See also

When and why, in the knowledge: `references/levers/tool_config.md`, `references/levers/new_tool.md`, `references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md`, `references/improving_agents/playbooks/wrong-tool-chosen.md`, `references/improving_agents/playbooks/failure-at-a-tool-call.md`, `references/improving_agents/playbooks/malformed-tool-calls.md`, `references/improving_agents/playbooks/missing-context-the-agent-could-be-given.md`, `references/improving_agents/techniques/cap-and-preview-wrapper.md`, `references/improving_agents/techniques/consolidate-tools.md`, `references/improving_agents/techniques/directive-in-the-tool-response.md`, `references/improving_agents/techniques/errors-the-agent-can-act-on.md`, `references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md`, `references/improving_agents/techniques/new-tool-description.md`, `references/improving_agents/techniques/normalize-inputs-wrapper.md`, `references/improving_agents/techniques/remove-or-scope-tools.md`, `references/improving_agents/techniques/roll-up-tool.md`, `references/improving_agents/smells/fixed-call-chain.md`, `references/improving_agents/smells/general-query-tool-without-a-guide.md`, `references/improving_agents/smells/too-many-tools.md`, `references/improving_agents/smells/tool-results-flood-the-context.md`, `references/improving_agents/smells/tool-search.md`, `references/improving_agents/smells/tools-on-a-live-server.md`, `references/improving_agents/smells/unnecessary-tools.md`, `references/improving_agents/smells/very-long-tool-description.md`.
