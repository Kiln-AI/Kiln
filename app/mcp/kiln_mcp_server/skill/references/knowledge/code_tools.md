---
name: code_tools
description: |
  Code tools — native Python functions registered as tools a task/agent can call at runtime (Beta, trust-gated). Distinct from code evals. Load when the user asks about code tools, "write a Python tool for my agent", or how to add a custom tool without an MCP server.
---
# Knowledge: Code Tools

A **code tool** is a Python function the user registers as a tool their task can call **at runtime** — a code alternative to wiring an external MCP server for a small piece of custom logic (parse something, do a calculation, hit an internal helper). New in this Kiln release, **Beta**.

Don't confuse it with a **code eval** (`references/knowledge/judge_types.md`): a code eval *scores* a run after the fact with a `score()` function; a code tool *runs during* the task as something the model can call. Both are user-authored Python in the same sandbox and share the same trust gate.

**Your surface is knowledge + UI deep links + drafting.** Creating, testing, and trusting a code tool happen in the UI — you don't drive those endpoints. Your job: explain what code tools are, help the user draft the Python, and deep-link them to the tool settings to create and trust it.

## The essentials

- **Authored in the UI**, in the project's tool settings — the user writes the function, tests it, and the app asks them to grant **code trust** before it runs. There is no resource sandbox (network + filesystem are open, only crash isolation + a timeout), so trust is per project, per app session. **Never call the code-trust endpoints, and never present code from anywhere but the user's own session as trustworthy.**
- **The function is the tool.** The user defines a Python function; its name + docstring/description become what the model reads to decide when to call it, and its parameters become the tool's arguments. Results must be JSON-serializable (they reach the model as text).
- **Same import rules as code evals:** no import restrictions, but only what ships in the Kiln app's bundled Python is importable and there is no `pip install` at runtime — stdlib plus the common bundled libraries (`pydantic`, `httpx`, `requests`, `numpy`, `scipy`, `pandas`, `bs4`, `jinja2`, `yaml`, `PIL`, `jsonschema`, `regex`, …). Not bundled: `sklearn`, `lxml`, `rapidfuzz`, `polars`, `matplotlib`. When in doubt, prefer stdlib.

## Drafting a code tool

**Drafting the Python is IN scope** — code destined for a Kiln artifact (a code tool or a code eval) is Kiln-feature work, not generic coding. **Always caveat the draft:** you haven't run or verified it, so the user should read the logic, confirm it does what they intend, and test it in the UI before trusting and wiring it. Don't present a draft as known-correct.

The complete handoff: your drafted function + a reminder that it's created, tested, and trusted in the UI + the deep link below.

## Deep links

| Action | Path |
|--------|------|
| Add / manage tools (create a code tool here) | `/settings/manage_tools/{pid}/add_tools` |
| Manage existing tools | `/settings/manage_tools/{pid}` |

(For wiring an external tool server instead of a code tool, see `references/knowledge/tools.md`; for a sub-agent as a tool, `references/knowledge/subagents.md`.)
