---
name: code_tool_authoring
description: How to write a code tool for the subject task as an experiment - when a tool is the right change, the four kinds of tool, the eight wrapper templates, the allowlist rule, the code contract, the calls, the build rules and a worked example. Read it before you build a new tool or a wrapper for a task's agent.
---

# Authoring a code tool for an experiment

This file is for a code tool that you build as a change to an agent: a new
tool, or a wrapper of a tool that the agent already has (it trims, previews,
batches, combines, validates or guards). The tool goes on ONE new run
config, beside the baseline, under the rules of the lever
`references/levers/new_tool.md`. The tool surface is where the subject model
decides: a wrapper can change what the model sees (smaller responses,
previews, batch calls, validated inputs) with no change to the prompt or the
model. For what code tools are, trust, and the plain create, test and
attach steps, read `references/knowledge/code_tools.md` first.

## When a tool is the right change

Reach for a code tool when the failure is **mechanical**: the model calls
the wrong route, floods itself with rows, sends a malformed payload, makes
one call per item, or repeats an expensive fetch. Code can make the failing
move impossible or unnecessary. When the failure is **behavioural** (tone,
order, a policy it was shown and ignored), a prompt or a skill is usually
cheaper and more direct. A tool and a directive often go together: the tool
makes the right move possible, and one line of its description makes it
preferred. Put that line in the tool's description, not in the prompt: text
in a tool moves with the tool, so a later change of the tool set needs no
prompt change.

## What you can build

- **Wrappers that shape the response**: call the subject's tool and change
  what comes back before the model sees it. *A projection*: only the fields
  the task needs. *A preview with a cap*: the total, the first N rows, and
  how to get the rest. *Errors the model can act on*: a not-found that lists
  the nearest valid values.
- **Wrappers that change the call pattern**: *a batch with an error per
  item*, so a partial success is usable; *a composite* that does a
  multi-step idiom in one call (resolve a display number to its id, then
  fetch the record); *write, then verify*: do the write, read the record
  back, return both.
- **Guard wrappers** that take a capability away: a read-only variant of a
  read-write tool, a cap on scope, a confirmation token for a destructive
  method.
- **New tools of pure code**, with no nested call: date math, dedup and
  diff, rendering a table or a report, a static context tool that returns
  identity, time or configuration as a tool response in place of prompt
  text. Context served on demand is a real lever, and variants of a context
  tool are cheap experiments.

The lever `references/levers/tool_config.md` covers the other side:
attaching or dropping existing tools on the new run config, with no new
code. A new description is not a `tool_config` change. It is a new tool: a
clone of a code tool with the new `tool_description`, or a wrapper of any
tool.

## Wrapper templates

When the failure in the trace is mechanical (wrong case, a display number
for an id, a body on a GET, one call per page or per item, a list that
floods the context, an error body the model cannot act on, a rule about a
tool that sits in the prompt and that the model breaks), reach for a
template BEFORE any prompt edit: the playbook
[change the surface, not the words](references/improving_agents/playbooks/change-the-surface-not-the-words.md).
Each template is a complete `run()` module, one for each class of failure:

| Failure in the trace | Template |
|---|---|
| Wrong case, wrong id form, a display number where an id goes, a string where a number goes | `references/knowledge/code_tool_wrappers/normalize_inputs.md` |
| One call per page, or a truncated list the model never notices | `references/knowledge/code_tool_wrappers/paginate_all.md` |
| One call per item, a loop that stops at the first error | `references/knowledge/code_tool_wrappers/batch_with_errors.md` |
| A list result floods the context | `references/knowledge/code_tool_wrappers/preview_and_cap.md` |
| A resolve-then-fetch idiom that the model gets wrong | `references/knowledge/code_tool_wrappers/composite_resolve_fetch.md` |
| Raw 4xx bodies the model cannot act on | `references/knowledge/code_tool_wrappers/actionable_errors.md` |
| A rule for a call, or for the reply after it, sits in the prompt, and the model breaks it before, with or after a tool call | `references/knowledge/code_tool_wrappers/context_on_tool_surface.md` |
| A read scenario produces a spurious write | `references/knowledge/code_tool_wrappers/readonly_guard.md` |

Three edits turn a template into the subject's tool: rename
`call_subject_api` to the wrapped tool's real function name; match its real
parameter schema (read it, never guess it: the calls below); and set the
routes and field names of the subject's API. Then the build rules below
apply unchanged.

Rules for every template:

- **The description carries half of the effect.** Say WHEN to prefer the
  wrapper over the tool it wraps, in the model's terms: "Prefer this
  whenever the user gave a shipment number instead of an id".
- **The `{status_code, body}` envelope.** A nested result arrives parsed OR
  as a JSON string, and the body inside can be a string again. Every
  template has `_parse` for this. Keep it.
- **Errors are data, not exceptions.** Return `{"ok": false, "error": ...}`
  with the guidance; a raised exception reaches the model as a traceback it
  cannot use. A nested tool that crashes raises out of the bridge too, so
  every template sends nested calls through `_call`, which turns a raise
  into `{"status_code": -1, "body": "<error>"}`. Keep it.
- **Each template states its `parameters_schema`** in its docstring. The
  parameter names of `run(...)` match it exactly. Numeric parameters are
  typed `["integer", "string"]`, because the model sends both, and the
  template coerces them.

## The allowlist rule

**A subject tool allowlists ONLY subject tools.** Never put
`kiln_tool::call_kiln_api`, or any tool that can reach the Kiln server, in
a subject tool's `tool_allowlist`: that hands the subject model a live
channel into the Kiln API (eval definitions, memories, run configs). Advice
to route HTTP through `tools.call_kiln_api` is for a tool built for an agent
that works on Kiln itself; for a subject tool it is exactly backwards. Never
a `kiln_tool::memory::...` tool either: it reads and writes the project's
memory store. The tools to wrap are the subject's tools already on the
parent run config, of any kind a run config attaches except skills: code
tools, MCP tools and built-in tools alike.

## The contract

- `code` (at most 64 KB) defines a module-level `run(...)`, sync or async.
  Its parameter names match `parameters_schema` (JSON Schema, root
  `type: object`): the schema is what the subject model fills in.
- Return a `str` (passed through), or a dict, list, number, bool or None
  (sent as JSON).
- **Nested calls**: `from kiln import tools` (or `async_tools`), then
  `tools.<function_name>(**kwargs)`. The kwargs match the wrapped tool's
  own parameter schema: read it from the code tool's GET
  (`parameters_schema`), or from the tool definition call (`parameters`)
  for an MCP, built-in, Kiln task or RAG tool. Every tool called is in
  `tool_allowlist`:
  - Kiln accepts code tool, MCP (remote and local), built-in, Kiln task,
    RAG, memory and OpenEnv tool ids (an OpenEnv tool resolves only inside
    an episode of its OpenEnv server). The allowlist rule above still
    applies to every kind.
  - Kiln refuses skill ids, `kiln_unmanaged::` ids, a duplicate id and the
    tool's own id.
  - Function names are unique in one allowlist, except among MCP tools: a
    call to a name that two MCP tools share fails as ambiguous.
  - Nested calls go at most 10 deep; at most 8 run at once in the process.
- `timeout_seconds` defaults to 60. Raise it for a batch or composite tool:
  all nested calls share one budget.
- Write `tool_description` for the subject model, not for people: the
  inputs, the outputs, and WHEN to prefer this tool over the tool it wraps.

## The calls

Read each endpoint doc before the first call.

| Step | Call |
|---|---|
| Read the trust state; grant trust | `references/knowledge/api_docs/get_api_projects_project_id_add_code_trust.md`; `references/knowledge/api_docs/post_api_projects_project_id_add_code_trust.md` |
| Read a code tool to clone | `references/knowledge/api_docs/get_api_projects_project_id_code_tools_code_tool_id.md` |
| Read the schema of a tool to wrap | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md`: `function_name`, `description`, `parameters` |
| Dry run (nothing is saved) | `references/knowledge/api_docs/post_api_projects_project_id_test_code_tool.md`: the create fields plus `params` (the arguments); the answer has `result`, `error`, `traceback`, `not_trusted`, `tool_call_log` |
| Create | `references/knowledge/api_docs/post_api_projects_project_id_code_tools.md`: `name`, `tool_function_name`, `tool_description`, `parameters_schema`, `code`, `timeout_seconds`, `tool_allowlist`, `provenance` |
| Put it on the new run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`, with `kiln_tool::code::<new_id>` in `tools_config.tools` |

Trust comes first: ask the user before you grant it, as
`references/knowledge/code_tools.md` says. An untrusted create or dry run
answers `not_trusted: true` and saves or runs nothing: check the field.

## Build rules for an experiment

1. **Add, never change.** Never archive or update a tool that another run
   config uses. The functional fields are fixed when the tool is created.
   The old tool stays live (the baseline uses it); you create a NEW tool
   and put it on YOUR run config only. When it *replaces* a tool, drop the
   old id from your run config: both ids on one run config means that the
   model chooses, which is a different experiment.
2. **A fresh `tool_function_name`.** Kiln refuses a run config, or an
   allowlist, in which two tools share a function name, so a variant that
   sits beside the tool it varies needs a new name. The name and the
   description are what the model decides by, so make the variant's "when
   to use me" explicit.
3. **Clone and modify.** GET the existing code tool, take its `code`,
   `parameters_schema` and allowlist as the base, change only what the
   hypothesis names, and create it as new. Write its `provenance`: the
   hypothesis in `notes`, the source tool in `derived_from_ids`.
4. **Test it, then dry-run it with reads only.** You can run the module on
   your own machine first, with a stub of `kiln.tools` (code tools in
   `references/knowledge/code_tools.md`). The dry run executes nested calls
   FOR REAL, and outside an eval a subject tool hits its live state: dry-run
   with harmless GETs or an id that does not exist (the plumbing and the
   error path, with no side effects). Never dry-run a write. Read
   `tool_call_log` in the answer: it shows each nested call's arguments and
   the start of its output, which is where a mismatch with the wrapped
   tool's signature shows.
5. **A tool that nobody is told about goes unused.** When the hypothesis
   needs the model to *prefer* the new tool, the usage directive (in the
   description, in preference to a prompt line) is part of the same change.
   Build it on the same run config, and say so when you report; do not
   quietly widen the hypothesis.

Say in the run config's provenance, and in your report, whether the
wrapper replaces the wrapped tool or sits beside it.

## A worked example: a composite wrapper

Users give the model display numbers; the API's path segments need opaque
ids; the baseline model guesses. The composite makes the resolve-then-fetch
idiom one call. `call_subject_api` stands for whatever the parent run
config's domain API tool is named: match its real signature and routes,
from its own definition. `<subject_api_tool_id>` is that tool's id on the
parent run config, of any kind (`kiln_tool::code::...`,
`mcp::local|remote::...`), but never `kiln_tool::call_kiln_api` (the
allowlist rule).

The create body:

```json
{
  "name": "Find record by display number",
  "tool_function_name": "find_record",
  "tool_description": "Resolve a display number, name, or other human-facing handle to its record: searches, disambiguates, and fetches in one call. Prefer this over call_subject_api whenever the user gave anything other than an opaque id.",
  "parameters_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "the handle exactly as the user gave it"}
    },
    "required": ["query"]
  },
  "timeout_seconds": 60,
  "tool_allowlist": ["<subject_api_tool_id>"],
  "code": "<the module of references/knowledge/code_tool_wrappers/composite_resolve_fetch.md as a string>"
}
```

Dry-run it with `params: {"query": "no-such-record-zzz"}`: the full
plumbing, both branches reachable, no side effects. Then create it, put
`kiln_tool::code::<new_id>` on the new run config, and run that run config
once on one or two train items to check that the agent calls the tool (the
technique's "Check that it took effect").
