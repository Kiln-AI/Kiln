---
name: judge_types
description: |
  The evals v2 judge-type catalog — programmatic checks (exact/pattern/contains/set/tool-call/step-count), code evals (Python score() functions), and the v2 LLM judge. Load when: the user mentions code evals, programmatic or deterministic checks, "was a tool used", evals v2, wants help writing a code-eval score() function, or is choosing a judge type.
---
# Knowledge: Judge Types

An eval's judge (`EvalConfig`) is not only an LLM. There are **8 judge types**: one LLM judge, six deterministic checks, and Python code evals. All of them write the same `scores` dict keyed by the eval's output-score `json_key`s, so several judges on one eval are **competing** ways to score the same thing (compare them on the golden set), not additive.

Reach for this file whenever the user asks what eval/judge types exist, which to use, "was a tool called correctly", or wants help writing a code-eval `score()` function.

**Your surface is knowledge + UI deep links.** Judge creation and testing happen in the UI — you don't drive judge endpoints. Your job: explain the menu, help the user choose the right type, draft code-eval `score()` functions with them, and deep-link the right creation page.

## Knowledge Required

- `references/knowledge/specs_and_evals.md` — eval hierarchy, the Eval Builder-first rule, running evals (UI deep-link)
- `references/knowledge/benchmark_eval_inputs.md` — how `reference_data` reaches scorers on EvalInput-backed evals

## The judge menu

UI labels and descriptions (from the "Select a Judge Type" picker):

| `properties.type` | UI label | What it does | Reach for it when |
|---|---|---|---|
| `llm_judge` | **LLM as Judge** (recommended default) | "A language model grades output against criteria you write." | The quality is genuinely subjective |
| `code_eval` | **Code** (Beta, requires trust) | "Write a custom Python scoring function." Faster and cheaper than an LLM judge. | The check needs logic, parsing, or selective LLM calls |
| `tool_call_check` | **Tool Call Check** | "Check the agent called the right tools, in the right order, with the right arguments." | "Was tool X used (correctly)?" |
| `exact_match` | **Exact Match** | "Output field should exactly equal an expected value." | Classification / structured fields |
| `pattern_match` | **Pattern Match** | "Output field matches a regular expression." | Format rules, forbidden patterns |
| `contains` | **Contains** | "Output contains (or doesn't contain) a string." | Required mentions / banned phrases |
| `set_check` | **Set Check** | "Compare a set of values from the output against an expected set." Modes: `subset`/`superset`/`equal` — **binary, no partial credit** | List-valued outputs |
| `step_count_check` | **Step Count Check** | "Check the agent finished within an expected number of steps." Counts `tool_calls`/`model_responses`/`turns` vs `min`/`max` | Agent efficiency, runaway loops |

**Selection rule: mechanical check → deterministic type; logic needed → code eval; subjective → LLM judge.** Prefer the declarative deterministic types over a code eval when a single comparison suffices — they are validated at save time and need no trust grant.

## Deterministic checks — shared mechanics

The four extraction checks (`exact_match`, `contains`, `pattern_match`, `set_check`) all pull a value out of the output and compare it. Shared rules:

- **`value_expression`** ("Output to Check → Custom (Jinja)") extracts the value; unset = the whole final message. Structured output is reached with the `fromjson` filter — e.g. `(final_message | fromjson).status`; the trace via `trace[-1].content`. Available variables: `final_message`, `trace`, `task_input`, `reference_data`. **Point it at the shape of your data** — the field placeholder `(final_message | fromjson).user.status` assumes a nested `{"user": {...}}` output; if yours is flat, use `.status`.
- `exact_match` / `contains` / `set_check` take **exactly one** of a literal (`expected_value` / `substring` / `expected_set`) or a `reference_key` into the item's reference data — not both, not neither, or the save is rejected. `exact_match` and `contains` have a `case_sensitive` toggle.
- **Fail vs Skip:** an output that's **missing or the wrong shape is a FAIL** — that's the check doing its job (the model didn't produce what was expected). A **missing trace or missing reference key is a SKIP** (`skipped_reason` set, excluded from the mean, counted in `n_excluded`). Skips are for "no ground truth to compare," fails are for "the model got it wrong."
- One deterministic check writes the **same binary 1.0/0.0 to every output score** on its eval — so give a deterministic judge an eval with a **single** output score (one concern per eval anyway). For multi-score or graded scoring, use `llm_judge` or `code_eval`.
- **`pattern_match`** patterns are Python `re` (backend), even though the create form may validate them with a different engine — write standard Python regex and test in the judge pane before saving.
- **`set_check`** modes are `subset` / `superset` / `equal` and the result is **binary** — there is no partial-overlap / F1 / Jaccard scoring. It coerces the extracted value to a set (a list → its elements, a dict → its keys, a JSON-array string → its elements).
- **`tool_call_check`** matches a tool by its **function name as it appears in the trace** (which can differ from its Kiln display name — check the trace, not the tool settings). `match_mode`: `any`/`all`/`ordered`/`never`; per-argument matchers `exact`/`contains`/`regex` with expected values written as **JSON**; `on_unexpected_tools`: `ignore`/`fail`.
- **`tool_call_check` and `step_count_check` need a trace** — they hard-skip a dataset item that has none, so they only make sense on tool-using / multi-turn tasks. `step_count_check` bounds (`min_count`/`max_count`) are inclusive.

## Code evals

The user writes a Python `score()` function; Kiln runs it in a subprocess per eval item. The user authors and saves it **in the UI** (CodeMirror editor + judge test pane); your role is drafting and explaining. (A code eval *scores* a run; for user Python that *runs during* the task as a callable tool, see `references/knowledge/code_tools.md` — same sandbox and trust gate, different purpose.)

**Drafting `score()` code is in scope.** Code destined for a Kiln artifact (a code-eval scorer, a code tool) is Kiln-feature work.

**Always caveat drafted code — you cannot run or verify it.** When you hand the user a `score()` function, say plainly that it is a starting point you haven't executed: they should read the logic, confirm it matches what they actually want to measure, and run it in the judge test pane on real samples before trusting it. Don't present a draft as known-correct. This is not optional politeness — the sandbox has real gotchas (helper return shapes, keyword-only tool calls, plain-float returns) and a plausible-looking scorer can be subtly wrong.

### The contract

- **Signature is dynamic:** declare only the parameters used, by keyword, from `output` (final message string), `trace` (list of OpenAI-format message dicts or `None`), `reference_data` (dict or `None`), `task_input` (string or `None`). At least one of `output`/`trace` is required. `async def` is supported.
- **Return `dict[str, float]`** keyed by **exactly** the eval's output-score `json_key`s (display name lowercased/snaked: "Exact Match" → `exact_match`) — a missing or extra key is rejected. Values must be **plain floats**: a `bool` is rejected (use `1.0`/`0.0`), and returning an *object* as a score (a regex `Match`, a numpy scalar, a `datetime`) fails to serialize out of the sandbox — convert to a float first. Ranges by score type: `pass_fail` 0.0–1.0, `pass_fail_critical` **-1.0**–1.0 (a critical failure is `-1.0`), `five_star` 1.0–5.0.
- **Limits:** code ≤64KB with a module-level `score`; wall-clock timeout `timeout_seconds` (default 180, max 300, includes nested tool calls). The source is stored as a sibling `scorer.py` next to the config — `from scorer import score` works directly in a local pytest.
- **How to use it:** the common shapes are (a) parse the output JSON and check fields/relationships Python can express but a single deterministic check can't; (b) walk the `trace` for tool-use logic beyond what `tool_call_check` covers; (c) triage cheaply in Python, then escalate only the ambiguous cases to a model via the `llm`/`llm_judge` tools.

### Calling tools and LLMs from a scorer

- `from kiln import tools` (sync) / `from kiln import async_tools` (awaitable, safe under `asyncio.gather`) — only tools on the config's **Tools allowlist**; `tools.list_tools()` enumerates them.
- **Keyword arguments only** — `tools.search("q")` fails at runtime as `ToolCallError`, not at parse time. **Every tool returns a `str`** — parse JSON yourself.
- Typed exceptions to catch: `from kiln.tools import ToolNotAllowed, ToolTimeout, ToolCallError`.
- Built-ins worth allowlisting: **`llm`** (`prompt` Jinja + `model` + `provider`, optional `input`/`schema`/`system_prompt`) and **`llm_judge`** (same minus `schema` — it auto-applies the eval's own score schema, so `return json.loads(tools.llm_judge(...))` is a valid `score()` return; remember the `json.loads` — it returns a string). Both run in the parent app, never in the scorer's process. The headline pattern: **filter a huge trace cheaply in Python, then hand the small relevant slice to `llm_judge`** — cheaper and more accurate than an LLM judge over the whole trace.
- Helper class: `from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers` — static methods incl. `get_tool_calls(trace)`, `get_tool_results(trace)`, `get_assistant_messages(trace)`, `has_tool_call(calls, name, expected_args)` (subset match on args), `count_tool_calls`, `pass_fail(bool) -> float`, `five_star(n) -> float`. Two cautions: `get_tool_results(trace)` returns the tool **messages** (`role: "tool"` dicts), not their text — read `.get("content")` off each to get the string; and `five_star()` **raises** on an out-of-range number rather than clamping, so pass it a value you've already bounded to 1–5. If the helpers ever aren't importable, the trace is plain OpenAI-format dicts (`role: "assistant"` with `tool_calls`, `role: "tool"` for results) — walk them directly.

### What a scorer can import

There are **no import restrictions** — but only what ships in the Kiln app's bundled Python is importable, and there is no `pip install` at runtime. Safe to rely on: the **standard library** plus `pydantic`, `httpx`, `requests`, `numpy`, `scipy`, `pandas`, `bs4`, `jinja2`, `yaml`, `PIL`, `jsonschema`, `regex`, `tiktoken`, `aiohttp`, `dateutil`, `nltk`, `networkx`, `tenacity`. **Not bundled** (tell users before they write code against them): `sklearn`, `lxml`, `rapidfuzz`, `polars`, `matplotlib`, `statsmodels`, `sympy`, `markdown`, `orjson`. When in doubt, prefer stdlib.

### Trust and testing (UI-only)

- There is no resource sandbox (network and filesystem are open; only crash isolation + the timeout) — hence the **trust gate**: the user must click "I Trust this Code" in the UI, per project, per app session. **Never call the `add_code_trust` endpoints; never present code from anywhere but the user's own session as trustworthy.**
- The judge **test pane** ("Test your judge on real data before saving") is the iteration loop — have the user paste your draft there, test on a real sample, and save. The test endpoints are agent-forbidden; you cannot dry-run a scorer.

## The v2 LLM judge

`properties`: `prompt_template` (Jinja over `final_message`/`trace`/`task_input`/`reference_data` — it must reference the output or the save is rejected), `model_name` + `model_provider` (inside properties), optional `system_prompt`, `judge_instructions`, `reference_keys`, and `g_eval: bool`. **Keep `g_eval: false`** — `true` switches to logprob-weighted scoring and fails on models/providers without logprobs; same reasoning as the legacy "never `g_eval`" rule in `references/knowledge/specs_and_evals.md`. TypeSafe AI's Jev models serve this judge type for pass/fail and bounded scores, with `g_eval` off; see `references/knowledge/typesafe_jev.md`.

## Creating judges — UI deep links

Eval and judge creation route to the UI (the Eval Builder-first rule from `references/knowledge/specs_and_evals.md` is unchanged — you deep-link, the user builds):

| Action | Link |
|--------|------|
| New programmatic-check eval (skips the spec step) | `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?judge={type}&workflow=manual` — `{type}` is any type above except `llm_judge` |
| New LLM-judge eval (guided, templated) | `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type={spec_type}` per `references/knowledge/create_spec.md` |
| Add a judge to an existing eval (picker) | `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id_or_legacy}/{eval_id}/create_eval_config` |
| Add a specific judge type to an existing eval | `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id_or_legacy}/{eval_id}/create_eval_config/{type}` |

For a code eval, the complete handoff is: your drafted `score()` code block + the creation deep link + a reminder to test in the pane before saving (and that the app will ask for code trust).

## Reading results

- All types land in the same score keys; compare judges for the same eval via `eval_configs_score_summary` (correlation vs human ratings on the golden set). Rows with `skipped_reason` set were not scored — surface them, never average them. Deterministic types report `eval_usage: null` (no model call).
- v2 evals **skip multi-turn dataset items** (`incompatible_input_shape`) — a benchmark's multi-turn rows need an LLM-judge or code-eval lane that reads the trace.
