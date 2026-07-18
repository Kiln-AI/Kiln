---
status: complete
---

# Code Judge LLM Calls — Project Overview

Add a feature to **code judges** (V2 `code_eval`): the ability for a code judge's Python to call an **LLM judge** from inside its `score()` function.

## Why

Often the trace or final message is way too verbose. A long trace can be 1M tokens+. Yet the judge is judging something like "was tool call X explicitly requested by the user", which can be filtered down to "the N user messages before calling X". That filtering is easy to build in code, and it's tiny compared to a 500k-token trace. But it still needs a subjective judge to look at the user messages — so a pure code judge today is no good.

## Goal

The ability for code judges to use LLM judges.

Pseudo code:

```python
prompt = "Check if the attached user messages justify calling the delete project. Requires explicit user consent.\n\nThe user messages\n```\n{input.user_messages}\n```"

def select_relevant_user_messages(...):
  ...

def score(trace, schema):
   user_messages = select_relevant_user_messages(trace)
   return helpers.judge_with_llm(prompt, input={"user_messages": user_messages}, "GPT 5.5", "openrouter", schema)
```

## Ergonomics (key priority)

Developer ergonomics are key.

- LLM-as-judges take a schema. The code judge already knows what schema it should produce (its eval output scores). It should be easy enough to wire that up.
- It should **not force** the schema. A code judge might use two judge calls: first a cheap sanity check, then a deeper call. It might want a custom schema. Or a cheap model checking "definitely safe, or maybe risky (worth a more expensive model to verify)?", then a more expensive model conditionally.
- See our existing helpers and their optional params. Ideally adding a schema isn't too much of a burden.

## Resolved direction (2026-07-18, scosman)

Rather than a bespoke judge bridge, we **reuse the `code_tools` sandbox bridge**: give code judges the same two-queue bridge + `tool_allowlist` that code tools have, and ship the capability as **two new built-in tools** selectable in the existing tool picker:

- **`llm`** — general-purpose LLM call. Optional `schema` (default none). No schema → text; schema → structured output. Generic.
- **`llm_judge`** — same, minus `schema`; auto-applies the code judge's own eval output-score schema and returns mapped float scores. Author supplies the prompt, so it's not a stock judge call (no judge caching/g_eval/prompt-templating).

Both are called via `from kiln import tools` (sync) / `async_tools` (async), execute **parent-side** (the sandbox never holds API keys or the Kiln stack), and always return a **string** (JSON for structured/scores; author `json.loads`). Full contract in `functional_spec.md`.
