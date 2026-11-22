---
name: code_tools
description: |
  Code tools — native Python functions registered as tools a task/agent can call at runtime (Beta, trust-gated). Distinct from code evals. Load when the user asks about code tools, "write a Python tool for my agent", or how to add a custom tool without an MCP server.
---
# Knowledge: Code Tools

A **code tool** is a Python function the user registers as a tool their task can call **at runtime** — a code alternative to wiring an external MCP server for a small piece of custom logic (parse something, do a calculation, hit an internal helper). New in this Kiln release, **Beta**.

Don't confuse it with a **code eval** (`references/knowledge/judge_types.md`): a code eval *scores* a run after the fact with a `score()` function; a code tool *runs during* the task as something the model can call. Both are user-authored Python in the same sandbox and share the same trust gate.

**You draft, test and create code tools through the API.** Your job: explain what code tools are, draft the Python with the user, test it, create it, and attach it to a run config. The user can also do this in the app's tool settings (deep links below).

## The essentials

- **Code trust comes first, and only from the user.** User-authored Python runs with no resource sandbox (network + filesystem are open, only crash isolation + a timeout), so the project needs **code trust** before a code tool runs; trust is per project, per app session. Read the state with `GET /api/projects/{project_id}/add_code_trust`. When the project is not trusted, **ask the user first**: say that the code will run on the machine where Kiln runs, with no sandbox, and grant trust (`POST /api/projects/{project_id}/add_code_trust`) only when they agree. **Never present code from anywhere but the user's own session as trustworthy.**
- **The function is the tool.** The user defines a Python function; its name + docstring/description become what the model reads to decide when to call it, and its parameters become the tool's arguments. Results must be JSON-serializable (they reach the model as text).
- **Same import rules as code evals:** no import restrictions, but only what ships in the Kiln app's bundled Python is importable and there is no `pip install` at runtime — stdlib plus the common bundled libraries (`pydantic`, `httpx`, `requests`, `numpy`, `scipy`, `pandas`, `bs4`, `jinja2`, `yaml`, `PIL`, `jsonschema`, `regex`, …). Not bundled: `sklearn`, `lxml`, `rapidfuzz`, `polars`, `matplotlib`. When in doubt, prefer stdlib.

## Drafting a code tool

**Drafting the Python is IN scope** — code destined for a Kiln artifact (a code tool or a code eval) is Kiln-feature work, not generic coding. **Always caveat the draft:** the user should read the logic and confirm it does what they intend. Don't present a draft as known-correct.

## Workflow: test, create, attach

Read `references/knowledge/api_docs/code_tools_api_list.md` and the doc of each endpoint before you call it.

1. **Check trust** as above.
2. **Test the draft** with `POST /api/projects/{project_id}/test_code_tool`, on inputs the user would expect. Fix the draft and test again until it behaves as intended. A test runs the code, so it needs trust too.
3. **Create it** with `POST /api/projects/{project_id}/code_tools`. The code cannot be changed after creation (`PATCH .../code_tools/{code_tool_id}` changes the name and description only); a new version is a new code tool, and the old one can be archived.
4. **Attach it** to a run config: list its tool ID in `tools_config.tools` of a new run config (`references/knowledge/model_create_configs.md`).
5. **Report** the code tool ID and the link to the tools page.

## Deep links

| Action | Link |
|--------|------|
| Add / manage tools (the user can create a code tool here) | `http://localhost:8757/tools/{project_id}/add_tools` |
| Manage existing tools | `http://localhost:8757/tools/{project_id}` |

(For wiring an external tool server instead of a code tool, see `references/knowledge/tools.md`; for a sub-agent as a tool, `references/knowledge/subagents.md`.)
