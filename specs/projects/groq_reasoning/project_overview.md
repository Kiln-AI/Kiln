---
status: draft
---

# Groq Reasoning

## Problem

Reasoning models on Groq are broken in Kiln today. Paid calls on `qwen_3p8_27b`, with LiteLLM 1.105.7, found three things ([evidence](../improve_reasoning/research/provider-verification/summary.md#7-groq-qwen-38-27b)).

- **Streamed tool loops fail on round 2.** Groq returns a 400:

  > `'messages.2' : for 'role:assistant' the following must be satisfied[('messages.2' : property 'reasoning_content' is unsupported)]`

  LiteLLM renames Groq's streamed `delta.reasoning` to `reasoning_content`. On the next round, Kiln sends the message back, and LiteLLM's Groq transform doesn't rename the field back.
- **Any multi-turn continuation after a streamed turn fails** with the same 400. That happens even with no tools, because the saved trace carries `reasoning_content`.
- **Non-streamed runs lose their reasoning.**
  - Groq returns it as `reasoning`. LiteLLM leaves it as an extra attribute, `message.reasoning`, and sets `reasoning_content` to `None`.
  - Kiln saves only `reasoning_content`, so the saved trace and `intermediate_outputs["reasoning"]` have no reasoning, and the UI shows none.
  - Within a run, the non-streamed tool loop still sends `reasoning` correctly, because the live LiteLLM message keeps the attribute.

Groq reads `reasoning` on input and rejects `reasoning_content`. Sending `reasoning` back adds exactly the earlier reasoning tokens to the input, so Groq uses it.

Kiln's paid streaming tests have no Groq case, which is likely why this wasn't caught.

## Goal

Groq reasoning models work streamed and non-streamed, in tool loops and across turns. Their reasoning is saved, shown in the UI, and sent back in the form Groq reads.

## Scope

- **Outbound:** on Groq, every assistant message sent, both live LiteLLM messages within a run and saved trace messages, carries its reasoning as `reasoning`, never `reasoning_content`.
- **Saving:** a non-streamed Groq reply's `message.reasoning` is saved as the trace's readable reasoning (`reasoning_content`), and reaches `intermediate_outputs["reasoning"]`.
- **Tests:**
  - offline tests with a fake Groq server, streamed and not;
  - a paid Groq case in the streaming, `return_on_tool_call` and multi-turn paid tests;
  - a Groq model in the pre-release whitelist.
- **Upstream:** report both LiteLLM behaviours: the streamed rename that isn't reversed on input, and the unmapped non-streamed `reasoning` field.

## Relationship to the improve-reasoning project

This was found during `specs/projects/improve_reasoning/`. It is split out because it is a live failure on `main` and should ship on its own. The improve-reasoning project's rule applies: Kiln deviates from LiteLLM only to fix confirmed wrong behaviour, and applies the fix to the in-run loop and to saved traces alike.
