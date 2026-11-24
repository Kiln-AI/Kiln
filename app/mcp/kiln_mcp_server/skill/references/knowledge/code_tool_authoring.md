---
name: code_tool_authoring
description: How to write a code tool for the subject task as an experiment lever - new tools and wrappers over the subject's existing tools (minify, preview, batch, compose, validate, guard) - when the tool lever is the right lever, the eight wrapper templates, allowlist hygiene, the contract, the calls, dry-run testing and the build discipline, with a complete worked example. Read it before you build a new_tool or tool_config experiment.
---

# Authoring a code tool for an experiment

You are building a code tool as an **experiment lever**: it ships wired into
ONE new run config, additive to the baseline, per your role's build
discipline (in a chat with a user: `references/knowledge/run_an_experiment.md`,
"Build the candidate"). The
tool surface is the subject model's decision point — a wrapper can reshape
what the model sees (smaller responses, previews, batch semantics,
validated inputs) without touching the prompt or the model. In a chat with
a user, read `references/knowledge/code_tools.md` first, for what code tools are, trust,
and the plain create, test and attach steps.

## When the tool lever is the right lever

Reach for a code tool when the failure is **mechanical** — the model calls
the wrong route, floods itself with rows, malforms a payload, loops one call
per item, or repeats an expensive fetch — because code can make the failing
move impossible or unnecessary. When the failure is **behavioral** (tone,
ordering, ignoring policy it was shown), prompt and skill levers are usually
cheaper and more direct. Tool + directive pairs are common: the tool makes
the right move possible, one description line makes it preferred. Put that
line in the tool's description, not in the prompt: text in a tool moves
with the tool, so a later change of the tool set needs no prompt change.

## What you can build

Four families:

- **Response-shaping wrappers** — call the subject tool, transform what
  comes back before the model sees it:
  - *projection / minifier*: return only the fields the task needs
    (token-diet);
  - *preview + cap*: materialize a big list, return `total` + first N + how
    to get the rest (flood control);
  - *error enrichment*: rewrite a raw error body into corrective guidance —
    e.g. a not-found that lists the nearest valid alternatives.
- **Call-pattern wrappers** — change how many calls a job takes:
  - *batch with per-item errors*: loop a list of specs, collect
    `{done, errors}` instead of raising, so partial success is usable;
  - *composite*: fuse a multi-step idiom into one call — resolve a
    display-number to its opaque id, then fetch the record;
  - *write-then-verify*: perform the write, read the record back, return
    both — making unverified-write failures structurally impossible.
- **Guardrail wrappers** — subtract capability instead of adding it: a
  read-only variant of a read-write tool (reject non-GET), a scope cap, a
  confirmation token required for destructive methods.
- **New pure-code tools** — no nested calls at all: date/window math,
  dedup/diff, table or report rendering, a static context tool that serves
  identity/time/config as a tool response instead of prompt text (context
  served on demand is a real lever — variants of a context tool are cheap
  experiments).

`tool_config` items (`references/levers/tool_config.md`) overlap this
space from the other side: attaching or dropping existing tools on the new
rc, no new code. A new description is not `tool_config`. It is a new tool:
a clone of a code tool with the new `tool_description`, or a wrapper of any
tool.

## Wrapper templates — bake it into code first

When the failure in the trace is MECHANICAL (wrong case, display number
for an id, a body on GET, one call per page or per item, a list that
floods the context, an error body the model cannot act on, a rule about a
tool that sits in the prompt, and the model breaks it), reach for a
template below BEFORE any prompt edit — the playbook
[change the surface, not the words](references/improving_agents/playbooks/change-the-surface-not-the-words.md).
The wrapper techniques of the knowledge say when each one applies. Eight
complete `run()` modules, one per failure class:

| Failure in the trace | Template | What it does for the model |
|---|---|---|
| Wrong case, wrong id form, display number instead of id, string where a number goes | `references/knowledge/code_tool_wrappers/normalize_inputs.md` | Accepts every variant, maps it, and on a value it cannot map returns the valid values instead of the API's error |
| One call per page, or a truncated list the model never notices | `references/knowledge/code_tool_wrappers/paginate_all.md` | Fetches every page up to a cap; returns `total`, `items`, `truncated`, `next_cursor` |
| One call per item, a loop that dies on the first error | `references/knowledge/code_tool_wrappers/batch_with_errors.md` | Runs a list of operations; returns `done` and `errors` so partial success is usable |
| A list result floods the context | `references/knowledge/code_tool_wrappers/preview_and_cap.md` | Returns `total`, the first N rows projected to the fields the task needs, and how to get more |
| Resolve-then-fetch idiom the model gets wrong | `references/knowledge/code_tool_wrappers/composite_resolve_fetch.md` | One call: search, disambiguate, fetch |
| Raw 4xx bodies the model cannot act on | `references/knowledge/code_tool_wrappers/actionable_errors.md` | Rewrites 400/404/405/422/429 into "what to do": valid values, nearest matches, "GET takes no body", "wait N s" |
| A rule for a call or for the reply after it sits in the prompt, and the model breaks it before, with or after a tool call | `references/knowledge/code_tool_wrappers/context_on_tool_surface.md` | A context tool whose DESCRIPTION carries the rule (when to call it, how the reply uses its result) and whose RESPONSE `notes` field states the tool's own status: derived facts, a fixable error, or how the tool works — never an order |
| A read scenario produces a spurious write | `references/knowledge/code_tool_wrappers/readonly_guard.md` | A read-only variant of a read-write tool; rejects every non-GET with the name of the write tool |

Three edits turn a template into the subject's tool: rename
`call_subject_api` to the wrapped tool's real function name, match its
real parameter schema (read it from the clone-source GET for a code tool,
or from the tool definition for an MCP, built-in, Kiln task or RAG tool —
never guess; "The calls" below), and set the subject's routes and field
names. The plumbing shape of each template is fixed; the subject-specific
edits are yours to dry-run (reads only, or a nonexistent id). Then the
build discipline below applies unchanged (fresh function name, dry-run
with reads, wire into the new rc, say in `build_notes` — in a chat with a
user, in your report — whether it replaces or sits beside the wrapped tool).

**Rules that apply to all of them:**

- **Allowlist only subject-task tools.** Never `kiln_tool::call_kiln_api`.
- **The wrapper replaces, or sits beside, the wrapped tool on the NEW rc
  only.** Both ids on one rc means the model chooses, which is a different
  experiment; say which in `build_notes` (in a chat with a user, in your report).
- **The description carries half of the effect.** Say WHEN to prefer the
  wrapper over the tool it wraps, in the model's terms: "Prefer this
  whenever the user gave a shipment number instead of an id".
- **`{status_code, body}` envelope.** Nested results arrive parsed OR as a
  JSON string, and the body inside can be a string again — every template
  carries `_parse` for that reason. Keep it.
- **Errors are data, not exceptions.** Return `{"ok": false, "error": …}`
  with the guidance; a raised exception reaches the model as a traceback
  it cannot use. A crashed NESTED tool raises out of the bridge too (a dry
  run against a missing database shows it), so every template routes
  nested calls through `_call`, which turns a raise into
  `{"status_code": -1, "body": "<error>"}`. Keep it.
- **Every template declares its `parameters_schema`** in the docstring.
  The `run(...)` parameter names must match it exactly; numeric parameters
  are typed `["integer", "string"]` because the model sends both, and the
  template coerces.
- **Dry-run with reads.** The dry run executes nested calls for real.

## The one hard rule: allowlist hygiene

**A subject-task tool may allowlist ONLY subject-task tools.** Never put
`kiln_tool::call_kiln_api` (or any tool that can reach the Kiln server)
into a subject tool's `tool_allowlist` — that hands the subject model a
live channel into the Kiln API (eval definitions, memories, run configs).
Advice to "route HTTP through `tools.call_kiln_api`" is for tools built
*for an agent that works on Kiln itself*; for a subject tool it is exactly
backwards. The wrap targets are the subject-task tools already on the
parent rc, of any kind a run config attaches except skills: code tools,
MCP tools and built-in tools alike. The rule above still applies to each
of them (the Contract below lists what Kiln accepts). Nested code-tool →
code-tool calls are supported, depth cap 10.

## Prerequisites

Code trust — in-memory per server process, so it is granted once per
session before authoring: grant it with your trust operation when you
have one. In a chat with a user, only the user grants it: read the state
(`references/knowledge/api_docs/get_api_projects_project_id_add_code_trust.md`) and follow
`references/knowledge/code_tools.md`. ⚠️ Untrusted create and dry-run
calls answer with **`not_trusted: true`** and persist or run nothing —
check the field.

## Contract

- `code` (≤64KB) defines module-level `run(...)` (sync or async); its
  parameter names must match `parameters_schema` (JSON Schema, root
  `type: object`) — the schema is what the subject model fills in.
- Return `str` (passthrough) or JSON-serializable dict/list/number/bool/None
  (auto-dumped).
- **Nested tool calls**: `from kiln import tools` (or `async_tools`) →
  `tools.<function_name>(**kwargs)` — kwargs must match the *wrapped*
  tool's own parameter schema. Read it from the clone-source GET (its
  `parameters_schema`) for a code tool, or from the tool definition
  (`parameters`) for an MCP, built-in, Kiln task or RAG tool; do not guess
  its signature. Every callee must be in `tool_allowlist`:
  - Kiln accepts code-tool, MCP (remote and local), built-in, Kiln task,
    RAG, memory and OpenEnv tool ids (an OpenEnv tool resolves only inside
    an episode of its OpenEnv server). The allowlist hygiene rule above
    still applies to every kind: never `kiln_tool::call_kiln_api`, and
    never a `kiln_tool::memory::…` tool, which reads and writes the
    project's memory store;
  - Kiln rejects skill ids, `kiln_unmanaged::` ids, a duplicate id, and the
    tool's own id;
  - function names must be unique in one allowlist, except among MCP tools:
    a call to a name that two MCP tools share fails as ambiguous;
  - depth cap 10; process concurrency cap 8.
- Nested results may arrive parsed OR as a JSON string — parse defensively,
  and note the *body inside* a `{status_code, body}` envelope may itself be
  a JSON string again.
- `timeout_seconds` defaults to 60 — size it up for batch/composite tools
  (N nested calls share one budget).
- Design `tool_description` for the subject model, not for humans: inputs,
  outputs, and WHEN to prefer this tool over the tool it wraps.

## The calls

Read each endpoint doc before the first call.

| Step | Endpoint doc |
|---|---|
| Dry-run (nothing persisted) | `references/knowledge/api_docs/post_api_projects_project_id_test_code_tool.md` — create fields + `params` (the invocation args) → `{result, error, traceback, not_trusted, tool_call_log, …}` |
| Create | `references/knowledge/api_docs/post_api_projects_project_id_code_tools.md` — `{name, tool_function_name, tool_description, parameters_schema, code, timeout_seconds, tool_allowlist}` |
| Read an existing tool (clone source) | `references/knowledge/api_docs/get_api_projects_project_id_code_tools_code_tool_id.md` |
| Read a non-code tool's schema (wrap target) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md` — `function_name`, `description`, `parameters` |
| Wire into the new rc | add `kiln_tool::code::<new_ctid>` to the new run config's `tools_config.tools` (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`) |

## Build discipline (the experiment deltas)

1. **Additive only — never archive or PATCH a tool another rc references.**
   Functional fields are immutable post-create; "create new + archive old"
   versioning is for a solo operator. In an experiment the old tool stays
   live (the baseline uses it); you create a NEW tool and wire it into
   YOUR rc only. If it *replaces* a tool, drop the old id from your rc's
   tool list — both ids on one rc means the model chooses, which is a
   different experiment.
2. **Fresh `tool_function_name`.** Tool names may repeat in a project, but
   Kiln rejects an allowlist with two tools of one function name, and a run
   of a run config whose tools share one fails, so a variant that sits
   beside the tool it varies needs a new name — and the name + description
   are what the model decides by, so make the variant's "when to use me"
   explicit.
3. **Clone-and-modify**: GET the existing code_tool, take its `code` /
   `parameters_schema` / allowlist as the base, change only what the
   hypothesis names, POST as new. Stamp the rc's provenance as usual.
4. **Dry-run first, reads only.** The dry run executes nested calls FOR
   REAL, and outside an eval episode a subject-domain tool hits its shared
   fallback state — so dry-run with harmless GETs or a nonexistent id
   (exercises plumbing + error path, zero side effects). Never dry-run a
   write. Read `tool_call_log` in the response — it shows each nested
   call's arguments and output preview, which is where signature
   mismatches with the wrapped tool surface. When you can run code on your
   own machine, you can first run the module with a stub of `kiln.tools`
   (`references/knowledge/code_tools.md`).
5. **A tool nobody is told about goes unused.** If the hypothesis needs the
   model to *prefer* the new tool, the usage directive (description text,
   in preference to a prompt line) is part of the same lever — build it in
   the same rc and say so in `build_notes` (in a chat with a user, in your report); do
   not silently widen the hypothesis.

## Worked example — a composite wrapper, complete

The shape: users hand the model display numbers; the API's path segments
need opaque ids; the baseline model guesses. The composite makes the
resolve-then-fetch idiom one call. `call_subject_api` stands for whatever
the parent rc's domain API tool is named; match its real signature and
routes, taken from its own definition. `<subject_api_tool_id>` is that
tool's id on the parent rc, of any kind (`kiln_tool::code::…`,
`mcp::local|remote::…`), but never `kiln_tool::call_kiln_api` (the rule
above).

Create payload:

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
  "code": "<the module below as a string>"
}
```

```python
import json


def _parse(r):
    # Nested results arrive parsed OR as a JSON string.
    if isinstance(r, str):
        try:
            return json.loads(r)
        except Exception:
            return {"status_code": -1, "body": r}
    return r


def run(query):
    from kiln import tools

    listing = _parse(tools.call_subject_api(
        method="GET", url_path="/api/v1/records",
        query_params={"q": query}))
    if listing.get("status_code") != 200:
        return {"found": False, "error": listing}
    body = _parse(listing.get("body"))  # the envelope's body can be a string too
    matches = body.get("results") or []
    if not matches:
        return {"found": False,
                "hint": f"no record matches {query!r}; try a shorter fragment"}
    if len(matches) > 1:
        return {"found": False, "ambiguous": [
            {"id": m.get("id"), "display": m.get("display_number"),
             "name": m.get("name")} for m in matches]}
    record = _parse(tools.call_subject_api(
        method="GET", url_path=f"/api/v1/records/{matches[0]['id']}"))
    return {"found": True, "record": record}
```

Dry-run with `params: {"query": "no-such-record-zzz"}` — full plumbing,
both branches reachable, zero side effects — then create, wire
`kiln_tool::code::<new_ctid>` into the new rc, and smoke per your role's build
discipline (in a chat with a user: run the new rc once on one or two train items and check that the agent calls the
tool: the technique's "Check that it took effect").

## Related

The build discipline this slots into — provenance, smoke, one-crack: your
role's build skill; in a chat with a user,
`references/knowledge/run_an_experiment.md` · every operation above: the
endpoint docs of "The calls" · rc composition + known bugs:
`references/knowledge/model_create_configs.md` and
`references/knowledge/create_task.md`.

## See also

When and why, in the knowledge: `references/levers/tool_config.md`, `references/levers/new_tool.md`, `references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md`, `references/improving_agents/playbooks/wrong-tool-chosen.md`, `references/improving_agents/playbooks/failure-at-a-tool-call.md`, `references/improving_agents/playbooks/malformed-tool-calls.md`, `references/improving_agents/playbooks/missing-context-the-agent-could-be-given.md`, `references/improving_agents/techniques/cap-and-preview-wrapper.md`, `references/improving_agents/techniques/consolidate-tools.md`, `references/improving_agents/techniques/directive-in-the-tool-response.md`, `references/improving_agents/techniques/errors-the-agent-can-act-on.md`, `references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md`, `references/improving_agents/techniques/new-tool-description.md`, `references/improving_agents/techniques/normalize-inputs-wrapper.md`, `references/improving_agents/techniques/remove-or-scope-tools.md`, `references/improving_agents/techniques/roll-up-tool.md`, `references/improving_agents/smells/fixed-call-chain.md`, `references/improving_agents/smells/general-query-tool-without-a-guide.md`, `references/improving_agents/smells/too-many-tools.md`, `references/improving_agents/smells/tool-results-flood-the-context.md`, `references/improving_agents/smells/tool-search.md`, `references/improving_agents/smells/tools-on-a-live-server.md`, `references/improving_agents/smells/unnecessary-tools.md`, `references/improving_agents/smells/very-long-tool-description.md`.
