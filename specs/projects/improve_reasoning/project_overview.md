---
status: complete
---

# Improve Reasoning

## Background

We added multi-turn to Kiln. When used, a trace is saved to a Kiln task run. On the next message it's reloaded, a new user message is appended, and it continues.

We have a series of issues to address.

### Reasoning

- Different providers do reasoning differently.
  - OpenAI, Gemini and Anthropic each have their own system (encryption, IDs, etc.) to prevent distillation attacks. These must be passed back, in exactly the right way, for the reasoning to continue.
  - Sometimes those providers return fake reasoning / reasoning summaries for the user to see, which are not the original reasoning (again, to prevent distillation).
- We want reasoning to be passed back for future turns (new user message turns, not only tool turns), so that they benefit from the reasoning context. Today it's not working.
- Reasoning summaries are nice as hints to the user, but should not impact next-turn inference, as they are not real reasoning. The real reasoning should go back via the provider-specific form (text, IDs, encrypted, etc.).

### Prompt caching effectiveness

- Similarly, the host must get the same messages, in the same order, with the same reasoning, down to the token, for prompt caching to work. It's not working today because reasoning isn't working.

## Design requirements

LiteLLM has these working if you `json.dumps` their objects (presumed; check in research). However, we have our own Chat Completions-style data model, for long-term stability, and because our UI and features rely on our data format being stable. We don't want to just dump LiteLLM objects and hope our UI can read them. So we need a design where:

- The core trace data structure is still OpenAI Chat Completions shaped, and Kiln controlled, so our UI and features can rely on key fields. It should also be possible to resume a trace pointed at a new provider/model; worst case it works while dropping unsupported reasoning (you can't pass encrypted OpenAI reasoning to another provider, but you can pass the messages).
- Provider differences for passing reasoning back and forth (actual strings, IDs, encrypted content, etc.) are handled. This should be exact, allowing prompt cache reuse.
- This is handled in the persistence layer. A chat can resume 30 minutes later; it is not just an in-memory loop like single turn is.

### Notes

- Single-turn tasks can loop over many tool calls, but that was all internal to LiteLLM, so we believe it always passed the right content for reasoning and prompt caching. This issue is essentially new for multi-turn, where we load a trace from disk and append new user messages instead of using the in-memory LiteLLM trace.
- We already have a special case for Cerebras in code for reasoning. This is a good sanity check: ideally it wouldn't be needed. We'd love to have no provider-specific logic (pending architecture).

### Open issue

- Should reasoning summaries (fake short reasoning) be stored as they are today, in the `reasoning` field, or moved to another field?

## Testing

The fix should have a series of `@paid` tests:

- Test that multi-turn works for both reasoning and prompt caching across multi-turn calls. Something like:
  - Reasoning: should pass back the right keys, and see reasoning in the trace that comes back.
  - Prompt caching: the cost/token count of the second call should reflect reasoning and prompt cache being used together properly.
- Add a subset (one model for each major provider) to the pre-release skill so we check this over time. It runs once per release. We want to make sure all providers work for reasoning and prompt cache reuse.

## Prior work

Existing planning and research: `specs/research/openai-responses-api/handoff_reasoning_across_turns.md` and `specs/research/openai-responses-api/reasoning-replay-by-provider.md`. Discussion during this project may overrule that planning.
