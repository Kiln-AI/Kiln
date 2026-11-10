# Harness-written tool calls and thinking models: what the documentation says

Date of research: 2026-11-10. Every source below was read on that date unless a different date is given.

This file reports documentation and source code only. It makes no design recommendation. A separate file in this folder, `live_probe.md`, covers live API behaviour.

Quotes are word for word. Two things were normalised: typographic apostrophes are written as plain ones, and link markup is removed. An ellipsis marks text left out.

## The scenario

The harness, not the model, decides to call a tool at the start of a turn. It runs the tool and then calls the model with a history that looks as if the model had made the call:

```
system
user("...")
assistant(tool_calls=[get_user_info()])   <- written by the harness: no thinking block, no reasoning item, no thought signature
tool(result)
-> the model is called here
```

## The three claims under test, and what the sources say

| Claim in the earlier note | What the current sources say |
|---|---|
| 1a. Anthropic returns 400 because "the final assistant message must start with a thinking block". | True only for the legacy manual mode (`thinking: {type: "enabled", budget_tokens}`), which exists only on Claude 4.6 and older models plus Claude Mythos Preview. The docs say adaptive thinking "drops that requirement". Every Claude model from 4.7 on rejects manual mode outright, so on those models the rule cannot apply. |
| 1b. Thinking config must stay fixed within an assistant turn. | The rule exists. The documented penalty for breaking it is that thinking is silently turned off for that request, not a 400. |
| 2. LiteLLM silently drops the `thinking` param when an assistant message with tool_calls has no thinking_blocks. | True only when `litellm.modify_params` is on. It is off by default, and this repo does not turn it on. The drop also needs every assistant message in the history to lack thinking blocks. |
| 3. Gemini 3 has a similar check through thought signatures. | True for Gemini 3 on `generateContent` and on the OpenAI-compatible endpoint: a 400. Google documents a dummy signature value for function calls the model did not generate. LiteLLM adds that dummy value by itself on its `gemini/` and `vertex_ai/` routes. |

## Summary table

"Harness call" below means an assistant tool call the harness wrote, with nothing attached, sitting in the current turn.

| Provider and thinking mode | What happens to the harness call | Documented workaround |
|---|---|---|
| Anthropic Messages API, manual extended thinking (Claude Opus 4.5, Sonnet 4.5, Haiku 4.5 and older; deprecated on Opus 4.6 and Sonnet 4.6; Claude Mythos Preview) | Docs: the API "enforces that the final assistant turn of a thinking-enabled request starts with a thinking block". Error reports from January to March 2026 show a 400. The same docs page also says turn conflicts make the API silently turn thinking off. The docs do not say which of the two applies here. | Turn thinking off for that turn, or use adaptive thinking on a model that has it. The docs give no way to create a thinking block. |
| Anthropic Messages API, adaptive thinking (Opus 4.6, Sonnet 4.6, and every model from 4.7 on) | Works. "Assistant turns don't need to start with a thinking block." | None needed. |
| Anthropic models with preserved thinking (Fable 5.1 and 5.2, Mythos 5.1 and 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5) | Works if the harness call is appended at the end and never changed or removed later. Inserting it before an existing thinking block, or editing or deleting it on a later request, makes later thinking blocks invalid: a 400, or the blocks are dropped. | Keep the history append-only. `prefix_mismatch_behavior: "drop_block"` (beta header `thinking-binding-controls-2026-08-01`) turns the 400 into dropped blocks. |
| Anthropic, forced `tool_choice` as an alternative | Manual mode: error. Adaptive mode: accepted, but the response has no thinking block. Opus 5.5, Sonnet 5.5, Fable 5.1 and 5.2, Mythos 5.1 and 5.2: 400 on every request. | `tool_choice: auto` plus a prompt instruction; strict tool use; structured outputs. |
| LiteLLM in front of Anthropic or Bedrock | Default (`modify_params` off): the request goes out unchanged. With `modify_params` on, and no assistant message carrying `thinking_blocks`: LiteLLM removes `thinking` and logs a warning. | `litellm.modify_params = True` or env `LITELLM_MODIFY_PARAMS`. |
| Gemini 3.x, `generateContent`, AI Studio and Vertex, at every thinking level including minimal | 400. The first function call part of each step in the current turn must carry its thought signature. | Set the signature to `skip_thought_signature_validator`. Google calls it "a last resort" that "will negatively impact model performance". An archived AI Studio page also lists `context_engineering_is_the_way_to_go`. |
| Gemini 3.x, OpenAI-compatible endpoint | Same check. The signature travels in `tool_calls[].extra_content.google.thought_signature`. | Same dummy value in that field (reported by third parties). |
| Gemini 2.5 | No 400 is documented. The Vertex page says Gemini 3 enforces "stricter validation ... than previous Gemini versions", and the archived AI Studio page names only Gemini 3 models for the 400. | None documented as needed. |
| Gemini Interactions API | Signatures sit on `thought` steps and "never appear on ... standard function calls". The docs do not cover a function call step the model did not produce. | Not documented. |
| LiteLLM in front of Gemini (`gemini/`, `vertex_ai/`) | LiteLLM adds the dummy signature to the first function call of an assistant message when the model is Gemini 3 or newer and no signature is present. | Built in; no setting. |
| OpenAI Responses API, reasoning models | No documented rule that a function call item needs a reasoning item unless the item came from a response. The known 400 names a response item id (`fc_...`) sent back without its reasoning item (`rs_...`). On "newer frontier models" the API drops reasoning items that follow a changed prefix; appending is fine. | Append only. Send back every output item of each response in order. |
| OpenAI Chat Completions | The API has no field for reasoning, so there is nothing to check. GPT-6 Astra and GPT-6.1 Sol do not support function calling on Chat Completions at all. | Use the Responses API for those models. |
| OpenRouter, Claude | Not documented for a missing `reasoning_details` in the current turn. OpenRouter states its requests "are not subject to" Anthropic's preserved thinking prefix check. | Not documented. |
| OpenRouter, Gemini 3 | 400 from OpenRouter: "Gemini models require OpenRouter reasoning details to be preserved in each request" (error text quoted in a GitHub issue). | Not documented. |
| DeepSeek thinking mode | 400: "The `reasoning_content` in the thinking mode must be passed back to the API." LiteLLM adds a one-space placeholder. | Third parties report an empty string is accepted. |
| Moonshot Kimi thinking models | 400: "thinking is enabled but reasoning_content is missing in assistant tool call message at index N". LiteLLM adds a one-space placeholder. | Not documented by Moonshot. |
| xAI Grok | Docs recommend sending encrypted reasoning back. No validation error is documented. | None needed. |

---

## 1. Anthropic

Sources, all read as raw Markdown from `platform.claude.com` on 2026-11-10:

- Thinking: https://platform.claude.com/docs/en/build-with-claude/thinking
- Steering thinking (the old adaptive thinking URL now serves this page): https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost
- Extended thinking (legacy): https://platform.claude.com/docs/en/build-with-claude/extended-thinking
- Preserved thinking: https://platform.claude.com/docs/en/build-with-claude/preserved-thinking
- Troubleshooting thinking: https://platform.claude.com/docs/en/build-with-claude/thinking-troubleshooting
- Thinking in tool and multi-turn workflows: https://platform.claude.com/docs/en/build-with-claude/thinking-tool-workflows
- Handle tool calls: https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
- Working with messages: https://platform.claude.com/docs/en/build-with-claude/working-with-messages
- Mid-conversation system messages: https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages
- Handling stop reasons: https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons
- API release notes: https://platform.claude.com/docs/en/release-notes/api (newest entry: November 9, 2026)

### 1.1 What an assistant message with `tool_use` needs when thinking is on

The rule depends on the thinking mode. From the Thinking page, section "Thinking with tool use":

> The entire turn runs in a single thinking mode: you can't toggle thinking in the middle of a turn, including during the tool-use loop. In extended (manual) mode, the API additionally enforces that the final assistant turn of a thinking-enabled request starts with a thinking block. Adaptive mode relaxes this: no assistant turn needs to start with one.

From the Extended thinking page, section "Turn structure in manual mode":

> Manual mode adds one requirement: the final assistant turn of a thinking-enabled request must start with a thinking block (adaptive thinking drops that requirement).

From the Steering thinking page, section "Turn validation":

> Assistant turns don't need to start with a thinking block. (Models using a legacy manual thinking budget enforce that the final assistant turn of a thinking-enabled request starts with one; see Turn structure in manual mode.)
>
> For multi-turn applications, this means you can pass back conversation history in whatever shape you have it:
>
> * Assistant turns that Claude produced without thinking are valid history as-is.
> * You can resume a conversation that started without thinking, or that used a different thinking configuration, without rewriting its history.
> * History assembled from mixed sources doesn't need thinking blocks reinserted at the start of each assistant turn to pass validation.
>
> The relaxation is about validation, not about what you should send. When you have thinking blocks, pass them back unmodified, particularly during tool use, where they carry the reasoning behind Claude's tool calls.

When thinking blocks do exist, they must come back unchanged. From the Thinking page, section "Preserving thinking blocks":

> * **Required:** within a tool-use turn, pass thinking blocks back.
> * **Recommended:** across turns, pass everything back.
> * **Allowed:** outside tool use, omit prior turns' thinking.

### 1.2 Error or silent downgrade

The Thinking page describes a silent downgrade for conflicts inside a turn:

> **Mid-turn conflicts degrade gracefully.** If you toggle thinking mid-turn (for example, between sending a tool call and returning its result), the API doesn't error. Instead, it silently disables thinking for that request. To preserve model quality, the API might strip thinking blocks that would create an invalid turn structure, or disable thinking when the conversation history is incompatible with thinking being enabled. To confirm whether thinking was active, check for the presence of `thinking` blocks in the response.

The same section says manual mode "additionally enforces" the thinking block at the start of the final assistant turn. The docs do not state which behaviour wins when a manual-mode request has a final assistant turn that starts with `tool_use`. The Troubleshooting page lists no error for a missing thinking block. It does list a 400 for changed blocks ("`thinking` or `redacted_thinking` blocks in the latest assistant message cannot be modified") and a 400 for an invalid signature.

Dated error reports for manual mode (secondary sources, GitHub, read through search excerpts):

- Kilo-Org/kilocode#5219, 2026-01-20, Vertex, `claude-opus-4-5@20251101`. The full error text:
  > messages.1.content.0.type: Expected `thinking` or `redacted_thinking`, but found `tool_use`. When `thinking` is enabled, a final `assistant` message must start with a thinking block (preceeding the lastmost set of `tool_use` and `tool_result` blocks). We recommend you include thinking blocks from previous turns. To avoid this requirement, disable `thinking`.
- Kilo-Org/kilocode#5131, 2026-01-16, Bedrock, Opus 4.5 and Sonnet 4.5: same error.
- anthropics/claude-code#16617, 2026-01-07, first-party API: same error.
- onyx-dot-app/onyx#9713, 2026-03-27, Bedrock through LiteLLM: same error.

No report dated after March 2026 was found.

### 1.3 Differences between modes and model generations

From the Troubleshooting page, table "Thinking support, defaults, and rejected configurations by model":

| Models | Thinking types | Default |
|---|---|---|
| Fable 5.2, Mythos 5.2, Fable 5.1, Mythos 5.1, Fable 5, Mythos 5, Opus 5.5 | Adaptive only | Always on |
| Opus 5, Sonnet 5, Haiku 5.5 | Adaptive only | On |
| Sonnet 5.5 | Adaptive, `between_tools` | On |
| Opus 4.8, Opus 4.7 | Adaptive only | Off |
| Opus 4.6, Sonnet 4.6 | Adaptive, extended (deprecated) | Off |
| Opus 4.5, Sonnet 4.5, Haiku 4.5 | Extended only | Off |
| Mythos Preview | Adaptive, extended | Always on |

From the Extended thinking page:

> Extended thinking (`thinking.type: "enabled"` with `budget_tokens`) is deprecated. Claude 4.7 and later models do not support it and reject requests that use it, returning a 400 error.

So the "must start with a thinking block" rule can only apply on Claude 4.6 and older models and on Mythos Preview, and only when the request uses a manual budget.

The Steering thinking page also describes when the model thinks under adaptive mode. This matters because the first real model call in the scenario comes right after a tool result:

> In a tool-use loop, the first request after new user input typically carries most of the reasoning, and follow-up requests that only process tool results can skip thinking, including at `xhigh` and `max`.

### 1.4 What counts as an assistant turn

From the Thinking page:

> **A tool-use loop is one assistant turn.** From the model's perspective, an assistant turn ends only when Claude completes its full response, which might include multiple tool calls and results.

The manual-mode error text locates the check at the "final `assistant` message ... (preceeding the lastmost set of `tool_use` and `tool_result` blocks)".

The three placement questions:

- **Harness exchange in an earlier, finished turn.** The manual-mode rule names only the "final assistant turn". The Thinking page says omitting earlier turns' thinking is "Allowed". The docs give no rule that an earlier turn must start with a thinking block.
- **User message that holds the tool result and new text.** The docs say text after tool results is allowed and where it goes: "the `tool_result` blocks must come FIRST in the content array. Any text must come AFTER all tool results." The same note says, in the context of server tools: "Text after the results ends the turn early". The stop reasons page lists as a cause of empty responses: "Adding text blocks immediately after tool results (the history then shows user text after every tool result, so Claude ends its turn to follow that pattern)". No page says whether the manual-mode thinking check treats such a message as the start of a new turn.
- **Harness exchange before the user's real message.** Not covered by the docs.

### 1.5 Supported ways to insert a tool call the model did not generate

No dedicated feature exists. Three passages allow assistant content that Claude did not write.

From Working with messages:

> Earlier conversational turns don't necessarily need to actually originate from Claude. You can use synthetic `assistant` messages.

From the Preserved thinking FAQ:

> **My harness can route a turn to a non-Claude model. Do those turns invalidate Claude's earlier thinking?**
> No, provided they're appended after the existing history and nothing earlier changes: an assistant message without thinking blocks is an appended message like any other. Send the other model's output as `text` and `tool_use` content.

From the Preserved thinking table "What counts as an edit" (it applies to Fable 5.1 and 5.2, Mythos 5.1 and 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5):

| Change between requests | Later thinking blocks |
|---|---|
| Append messages at the end | Valid |
| Edit, reorder, or delete any earlier `user`, `assistant`, or `system` message | Invalid |
| Add a text block to an earlier user turn, or remove one you added last time | Invalid |
| Change any request parameter outside `system`, `tools`, and `messages` (including `tool_choice`) | Valid |

Enforcement of that prefix check, from the same page: Fable 5.2, Mythos 5.2 and Mythos 5.1 return a 400 on every account. Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5 return a 400 on accounts created on or after 2026-08-31 and let failing blocks through on older accounts. The release note of November 9, 2026 confirms the Fable 5.2 rule.

Related points:

- **Prefill.** "Claude 4.6 and later models and Claude Mythos Preview reject a prefilled final assistant turn with a 400 error, whether or not thinking is on." The scenario ends with a user message that holds a tool result, so it is not a prefill.
- **Message shape.** "Tool result blocks must immediately follow their corresponding tool use blocks in the message history. You cannot include any messages between the assistant's tool use message and the user's tool result message."
- **Mid-conversation system messages.** These are the documented channel for operator text, not for tool output: "Do not use it to pass tool output, retrieved documents, or other third-party content; keep that content in `tool_result` blocks". A system message cannot sit "between an `assistant` `tool_use` block and the `tool_result`".
- **Server tools.** These run on Anthropic's side and produce their own blocks. No page describes using them to stand in for a harness-run tool.

### 1.6 Forced `tool_choice` with thinking

From the Thinking page, section "Response prefill and forced tool use":

> Forced tool use (`tool_choice: {"type": "any"}` or `{"type": "tool", ...}`) is incompatible with manual extended thinking but works with adaptive thinking. The exceptions are Claude Opus 5.5, Claude Sonnet 5.5, Claude Fable 5.2, Claude Mythos 5.2, Claude Fable 5.1, and Claude Mythos 5.1, which reject forced tool use on every request with a 400 error. On those models, use `tool_choice: {"type": "auto"}` with strict tool use or structured outputs instead. Where forced tool use is accepted, the response starts with the tool call and has no `thinking` block.

Release notes date the 400 on forced tool use to September 1, 2026 (Fable 5.1, Mythos 5.1), September 22, 2026 (Opus 5.5) and September 28, 2026 (Sonnet 5.5).

---

## 2. Google Gemini

Sources:

- Vertex page "Thought signatures", "Last updated 2026-11-05 UTC": https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking/thought-signatures (read through a fetch service)
- AI Studio "Thought signatures" and "Gemini thinking": https://aistudio.google.com/docs/thought-signatures and https://aistudio.google.com/docs/thinking (read through a fetch service)
- AI Studio "OpenAI compatibility": https://aistudio.google.com/docs/openai
- Archived copy of the older AI Studio page, snapshot of 2026-01-13: https://web.archive.org/web/20260113214539/https:/ai.google.dev/gemini-api/docs/thought-signatures (read through search excerpts only)

### 2.1 The validation rule and the error

From the Vertex page:

> Gemini 3 models enforce stricter validation on thought signatures than previous Gemini versions because they improve model performance for function calling. To ensure the model maintains full context across multiple turns of a conversation, you must return the thought signatures from previous responses in your subsequent requests, even when using `MINIMAL` thinking levels. If a required thought signature is not returned when using Gemini 3 models, the model will return a `400` error.

> **Rule**: When constructing the next request, you must include the `part` containing the `functionCall` and its `thought_signature` *exactly* as it was returned by the model. For sequential (multi-step) function calling, validation is performed on all steps in the current turn, and omitting a required `thought_signature` for the first `functionCall` part in any step of the current turn results in a `400` error. A turn begins with the most recent user message that is not a `functionResponse`.

From the archived AI Studio page:

> Validation: Strict validation is enforced for all function calls within the current turn. (Only current turn is required; we don't validate on previous turns)
> - The API goes back in the history (newest to oldest) to find the most recent User message that contains standard content (e.g., `text`) (which would be the start of the current turn). This will not be a `functionResponse`.

Error texts as quoted in GitHub issues:

- Vertex: "Unable to submit request because function call `default_api:xxx` in the 12. content block is missing a `thought_signature`." (pydantic/pydantic-ai#3881, 2025-12-29)
- AI Studio: "Function call is missing a thought_signature in functionCall parts. This is required for tools to work correctly, and missing thought_signature may lead to degraded model performance." (google/adk-python#7438)

The Vertex page lists one exception: "Gemini 3 Pro Image doesn't return a `400` error if a thought signature isn't returned."

A comment in google/adk-python#7438 describes the turn boundary in practice: "Gemini 3 checks signatures only for function calls in the current turn. If a user-role message follows the function response ... the call no longer counts as the current turn and the request succeeds, though without the signature."

### 2.2 The escape hatch for function calls the model did not generate

From the Vertex page:

> There are rare cases where you need to provide `functionCall` parts that were not generated by the API and therefore don't have an associated thought signature (for example, when transferring history from a model that does not include thought signatures). You can set `thought_signature` to `skip_thought_signature_validator`, but, this should be a last resort as it will negatively impact model performance.

From the archived AI Studio page, FAQ 1. This passage names the harness case directly:

> While injecting custom function call blocks into the request is strongly discouraged, in cases where it can't be avoided, e.g. providing information to the model on function calls and responses that were executed deterministically by the client, or transferring a trace from a different model that does not include thought signatures, you can set the following dummy signatures of either `"context_engineering_is_the_way_to_go"` or `"skip_thought_signature_validator"` in the thought signature field to skip validation.

### 2.3 The OpenAI-compatible endpoint

The Vertex page gives Chat Completions examples in which the signature sits at `tool_calls[].extra_content.google.thought_signature`, and it says of the multi-step example: "you must include signatures for *all* function calls in this loop". Third-party reports of a 400 on this endpoint when the field is missing: inference-gateway/inference-gateway#229 and google/adk-python#7438.

The current AI Studio "OpenAI compatibility" page does not mention thought signatures.

### 2.4 The Interactions API

The AI Studio docs now treat the Interactions API as the default and call `generateContent` "a legacy API" (https://aistudio.google.com/docs/llms.txt). From the AI Studio thinking page:

> In the Interactions API, thoughts are a first-class representation as dedicated `thought` steps. Because of this signatures are limited exclusively to two known locations, `thought` steps, or built-in tool steps ... They never appear on user inputs, model outputs, or standard function calls.

> You **MUST** always resend all `thought` blocks exactly as they were received from the model.

The page says nothing about a function call step that has no thought step before it.

---

## 3. OpenAI

Sources (the OpenAI docs host could not be reached directly; pages were read through a fetch service):

- Reasoning models: https://platform.openai.com/docs/guides/reasoning
- Function calling: https://platform.openai.com/docs/guides/function-calling
- Conversation state: https://developers.openai.com/api/docs/guides/conversation-state
- Keep the prefix unchanged: https://developers.openai.com/api/docs/guides/preserved-reasoning
- Prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching

### 3.1 Responses API

From the Function calling guide:

> Note that for reasoning models like GPT-5 or o4-mini, any reasoning items returned in model responses with tool calls must also be passed back with tool call outputs.

From the Reasoning guide, section "Keeping reasoning items in context":

> When doing function calling with a reasoning model in the Responses API, pass back the reasoning items returned with the function calls along with the tool outputs. ... If you manage conversation history yourself, include the original input and all output items from each response in the input of the next request. Keep those items in their original order and append new items.

Both passages speak of reasoning items "returned" by the model. Neither covers a function call item the developer wrote.

The known error names two response item ids. As quoted in deepset-ai/haystack#10390 (2026-01-15):

> Item 'fc_0cd1...' of type 'function_call' was provided without its required 'reasoning' item: 'rs_0cd1...'.

Secondary evidence that the check is tied to the item id: vercel/workflow#880 reports the error when a tool call carries `providerOptions.openai.itemId` and no error "when `itemId` is omitted". The official Prompt caching guide shows, in its "Multi-turn agent" example for `gpt-6.1-sol` with reasoning on, a `function_call` input item that has only `call_id`, `name` and `arguments`, with no `id` and no reasoning item before it.

From "Keep the prefix unchanged":

> Starting with newer frontier models, the API will drop reasoning items that follow a prefix edit. When reasoning items are dropped, the model may have to redo some reasoning, which can increase token usage, cost, and latency.

> To get the best performance from our models, we recommend avoiding changes to the prefix and adopting an append-only integration pattern as far as possible.

The page describes dropping, not an error, and does not name the models.

### 3.2 Chat Completions

Chat Completions has no reasoning items. From the Reasoning guide:

> Use the Responses API for function calling. Chat Completions does not support function calling with GPT-6 Astra or GPT-6.1 Sol.

---

## 4. LiteLLM

Sources:

- Installed package in this repo: `litellm` 1.102.0 (PyPI upload 2026-09-20), pinned by `libs/core/pyproject.toml` as `litellm>=1.102.0,<1.103`.
- Latest release: `litellm` 1.108.4 (PyPI upload 2026-11-09). The functions below are the same in both versions.
- Docs: https://docs.litellm.ai/docs/reasoning_content and https://docs.litellm.ai/docs/providers/gemini

### 4.1 Anthropic and Bedrock: dropping `thinking`

`litellm/llms/anthropic/chat/transformation.py`, `AnthropicConfig.transform_request` (the same block is in `litellm/llms/bedrock/chat/converse_transformation.py`):

```python
if (
    optional_params.get("thinking") is not None
    and messages is not None
    and last_assistant_with_tool_calls_has_no_thinking_blocks(messages)
    and not any_assistant_message_has_thinking_blocks(messages)
):
    if litellm.modify_params:
        optional_params.pop("thinking", None)
        litellm.verbose_logger.warning(
            "Dropping 'thinking' param because the last assistant message with tool_calls "
            "has no thinking_blocks. The model won't use extended thinking for this turn."
        )
```

Facts from the code:

- The helpers are in `litellm/utils.py`. `last_assistant_with_tool_calls_has_no_thinking_blocks` looks at the last assistant message with `tool_calls` anywhere in the history, not only in the current turn.
- The drop does not happen if any assistant message has `thinking_blocks`. Then the request goes to Anthropic unchanged.
- `litellm/__init__.py`: `modify_params = bool(os.getenv("LITELLM_MODIFY_PARAMS", False))`. The default is off.
- With `modify_params` off, the block does nothing.
- The condition tests for any `thinking` value. It is not limited to `type: "enabled"`.
- For Claude models with adaptive thinking, LiteLLM maps `reasoning_effort` to `thinking: {type: "adaptive", display: "summarized"}` (`AnthropicConfig._map_reasoning_effort`). Anthropic's docs say that on models where thinking is on by default, a request with no `thinking` field still runs adaptive thinking. So removing the field does not turn thinking off on those models.
- This repo has no use of `modify_params` or `LITELLM_MODIFY_PARAMS` outside the virtual environment. `libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py` passes `drop_params: True`.

From the LiteLLM docs page "Reasoning Content":

> LiteLLM can automatically handle this incompatibility when modify_params=True is set. If the client sends a request with thinking enabled but the assistant message with tool_calls is missing thinking_blocks, LiteLLM will automatically drop the thinking param for that turn to avoid the error.

> When modify_params=True and LiteLLM drops the thinking param, the model will not use extended thinking for that specific turn.

### 4.2 Anthropic: forced tool choice

`litellm/llms/anthropic/common_utils.py`, `AnthropicModelInfo.forced_tool_use_downgraded`: for models flagged `supports_forced_tool_use: false`, a forced `tool_choice` is changed to `auto` when `drop_params` is on, and raises a client-side 400 when it is off. The warning text: "Downgrading forced tool_choice to 'auto' for model=%s (drop_params=True): this model rejects tool_choice type 'any'/'tool' with a 400 because thinking is always on and a forced call would skip it."

### 4.3 Gemini: dummy thought signature

`litellm/litellm_core_utils/prompt_templates/factory.py`:

```python
def _get_dummy_thought_signature() -> str:
    ...
    dummy_data: Final = b"skip_thought_signature_validator"
    return base64.b64encode(dummy_data).decode("utf-8")
```

In `convert_to_gemini_tool_call_invoke`:

```python
needs_dummy_signature: Final = model is not None and VertexGeminiConfig._is_gemini_3_or_newer(model)
...
thought_signature = _get_thought_signature_from_tool(dict(tool))
is_first_function_call = len(_parts_list) == 0
if not thought_signature and is_first_function_call and needs_dummy_signature:
    thought_signature = _get_dummy_thought_signature()
```

Facts from the code:

- The dummy value is added only to the first function call of an assistant message, and only for models that `_is_gemini_3_or_newer` accepts.
- LiteLLM looks for a real signature in `provider_specific_fields.thought_signature` on the tool call or its function, and in the tool call id (`call_<id>__thought__<signature>`).
- This code is on the native Gemini path (`gemini/` and `vertex_ai/`). LiteLLM's OpenRouter provider has no signature handling.

### 4.4 Other providers in LiteLLM

- DeepSeek, `litellm/llms/deepseek/chat/transformation.py`, `_fill_reasoning_content`: when thinking mode is active, every assistant message without `reasoning_content` gets a single space, with a warning.
- Moonshot, `litellm/llms/moonshot/chat/transformation.py`, `fill_reasoning_content`: for reasoning models, every assistant message with `tool_calls` and no `reasoning_content` gets a single space, with a warning.
- OpenAI Responses bridge, `litellm/completion_extras/litellm_responses_transformation/transformation.py`: an assistant tool call becomes `{"type": "function_call", "call_id": <tool call id>, "name": ..., "arguments": ...}` with no item `id`. Reasoning items are added before it only if the message carries `reasoning_items` or `thinking_blocks`.

---

## 5. OpenRouter

Sources, read directly from `openrouter.ai` on 2026-11-10:

- Reasoning Tokens: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
- Claude 5.5 and Fable 5.1 migration guides: https://openrouter.ai/docs/cookbook/evaluate-and-optimize/model-migrations/claude-5-5 and `.../fable-5-1`

On keeping reasoning:

> Preserving reasoning blocks is useful specifically for tool calling. When models like Claude invoke tools, it is pausing its construction of a response to await external information.

> When providing reasoning_details blocks, the entire sequence of consecutive reasoning blocks must match the outputs generated by the model during the original request; you cannot rearrange or modify the sequence of these blocks.

The page does not say what happens when a tool call in the current turn has no `reasoning_details`.

On Anthropic's preserved thinking check, from the Claude 5.5 migration guide:

> **Requests through OpenRouter are not subject to this enforcement**, as with Fable 5.1. History edits that would 400 against the Anthropic API directly succeed through OpenRouter.

On forced tool use, same guide: "Forced tool use still works on Haiku 5.5 ... but the model skips thinking before a forced call."

For Gemini 3, the error OpenRouter returns when reasoning details are missing, as quoted in OpenRouterTeam/ai-sdk-provider#239:

> Gemini models require OpenRouter reasoning details to be preserved in each request. Please refer to our docs: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens#preserving-reasoning-blocks. Upstream error: ... function call `default_api:readFile` in the 2. content block is missing a `thought_signature`.

No OpenRouter page describes a dummy signature.

---

## 6. Other providers

Only Moonshot and xAI rows rest on primary docs. The DeepSeek docs host timed out, and the other vendors' docs were not read, so those rows come from secondary sources.

| Provider | Rule for reasoning in a tool loop | If it is missing | Source |
|---|---|---|---|
| DeepSeek thinking mode | `reasoning_content` must be sent back on assistant messages in the tool loop | 400: "The `reasoning_content` in the thinking mode must be passed back to the API." | LiteLLM source comment; microsoft/agent-framework#2603 quoting DeepSeek's docs; anrouter.com blog, 2026-09-27 |
| Moonshot Kimi (K2.5, K2.6, K2.7-code, K3, K3.1 Pro) | "For multi-turn conversations and tool calls, pass the complete assistant message returned by the API back to `messages` as-is (including `reasoning_content`)" | 400: "thinking is enabled but reasoning_content is missing in assistant tool call message at index 2" | https://platform.moonshot.ai/docs/guide/use-kimi-k2-thinking-model ; BerriAI/litellm#21672 and #26156 |
| xAI Grok | "Send encrypted reasoning back with every turn" on the Responses API. Chat Completions "has no field for the model's encrypted reasoning". | No error documented. The docs describe lost reasoning. | https://docs.x.ai/developers/model-capabilities/text/best-practices |
| Z.ai GLM | Reasoning must be kept with tool results in interleaved thinking; `clear_thinking: false` keeps it across turns | Not confirmed | CherryHQ/cherry-studio#17212 |
| MiniMax | The full assistant message, including `reasoning_details` or the think tags in `content`, must be kept | Not confirmed | CherryHQ/cherry-studio#17212 |
| Qwen, Mistral | Not confirmed | Not confirmed | No source read |

---

## 7. Prior art in other frameworks

### Frameworks that add Google's dummy signature

- **Pydantic AI**, `pydantic_ai_slim/pydantic_ai/models/google.py`, `_function_call_part_dict` (main branch, 2026-11-10). Source comment: "the documented dummy `skip_thought_signature_validator` works for both Gemini API and Google Cloud. It's also what a signature from the other transport is replaced with: both reject each other's, and both reject a first function call without one (verified live, 2026-10-27)." Background: pydantic/pydantic-ai#3881 (2025-12-29) reports that Vertex accepts only `skip_thought_signature_validator`.
- **LangChain, Python**, `langchain_google_genai/chat_models.py`, `_parse_chat_history` (main branch, 2026-11-10). Source comment: "Placeholder injected by `_parse_chat_history` when a function-call part for a Gemini 3+ model lacks a thought signature (e.g. replayed history or a cross-provider fallback)."
- **LangChain, JavaScript**, langchain-ai/langchainjs#10503: adds `"context_engineering_is_the_way_to_go"` for "manually constructed or cross-provider tool calls (which lack a signature)".
- **Cline**, `src/core/api/transform/gemini-format.ts`: `thoughtSignature: block.signature || GEMINI_DUMMY_THOUGHT_SIGNATURE`.
- **LobeHub**, `packages/model-runtime/src/core/contextBuilders/google.ts`: adds the dummy value to every function call without a signature.

### Google ADK

The ADK issues found are about signatures lost by the framework, not about calls injected by a callback: google/adk-python#3705, #4650 and #7438. A check of `flows/llm_flows/context/_contents.py`, `models/google_llm.py` and `models/lite_llm.py` on the main branch (2026-11-10) found no `skip_thought_signature_validator` string.

### Harness-style interception in front of Anthropic

- **LiteLLM web search interception**, BerriAI/litellm#21604. The proxy runs a tool itself and builds the follow-up assistant message. "When extended thinking is enabled, the websearch interception agentic loop builds a follow-up assistant message with only tool_use blocks. Anthropic's API requires assistant messages to start with thinking/redacted_thinking blocks when thinking is enabled, causing a 400 Bad Request." The fix carries the model's own thinking blocks into the follow-up message.
- **Onyx**, onyx-dot-app/onyx#9713 (2026-03-27): the app stops sending `thinking` whenever the history has an assistant message with `tool_calls`, because it does not store thinking signatures.
- **LangChain**, langchain-ai/langchain#34794 (2026-01-17): `SummarizationMiddleware` removed thinking blocks inside an active tool loop and got the same 400 on Claude Sonnet 4.5 with a manual budget.

### LangChain middleware `jump_to`

`libs/langchain_v1/langchain/agents/middleware/types.py` defines `JumpTo = Literal["tools", "model", "end"]`. No issue was found that ties `jump_to: "tools"` to a thinking-model failure.

### OpenAI Agents SDK and Vercel AI SDK

No documentation on harness-injected calls was found. Related issues: openai/openai-agents-js#791 (DeepSeek thinking mode rejects a tool-call message without `reasoning_content`) and vercel/workflow#880 (OpenAI rejects a tool call that carries an item id without its reasoning item).

---

## Where sources disagree or look stale

1. **Anthropic, manual mode.** One paragraph of the Thinking page says the API "enforces" a thinking block at the start of the final assistant turn. The next paragraph says turn conflicts make the API silently turn thinking off and "the API doesn't error". The page does not say which applies to a turn that starts with `tool_use`.
2. **LiteLLM default.** BerriAI/litellm#18787 describes the drop as happening "when `litellm.modify_params=True` (default)". The source sets the default to off.
3. **LiteLLM docs versus Anthropic docs.** The LiteLLM "Reasoning Content" page says a missing thinking block "will result in a 400 Bad Request error" without limiting this to manual mode. Its example sends `thinking: {type: "enabled", budget_tokens: 1024}` to `claude-sonnet-5`, a model that Anthropic's docs say rejects that value.
4. **Google AI Studio docs moved.** The current "Thought signatures" page describes only the Interactions API. The FAQ that names both dummy values was found only in the archived copy of 2026-01-13 and in third-party quotes. The Vertex page lists only `skip_thought_signature_validator`.
5. **Which dummy value works where.** pydantic/pydantic-ai#3881 says Vertex rejects `context_engineering_is_the_way_to_go`. CherryHQ/cherry-studio#19047 says the `skip_thought_signature_validator` string is documented for the OpenAI-compatible endpoint and "not for native `generateContent`". The Vertex page lists it under its REST rules.
6. **How the dummy value is encoded.** LiteLLM sends the base64 of the string. LangChain's Python code sends the raw string and its comment says base64 "would hide the bypass string from the API". Pydantic AI passes bytes to the Google SDK.
7. **DeepSeek.** A comment in zed-industries/zed#51743 says DeepSeek returns a 400 if `reasoning_content` is sent back. Other sources say thinking mode returns a 400 if it is not sent back. The sources name different models.
8. **Moonshot.** A third-party table (kai9000.com) says only `kimi-k2.6` with `thinking.keep="all"` needs `reasoning_content`. Moonshot's page and the LiteLLM issues show the 400 on K2.5 and K2.6 tool-call messages.
9. **OpenAI.** The Function calling guide says reasoning items "must" be passed back. The Prompt caching guide shows a function call item with no reasoning item on a reasoning model.

## Could not confirm

1. Whether Anthropic, today, returns a 400 or silently turns thinking off when a manual-mode request has a final assistant turn that starts with a harness-written `tool_use`. The latest dated 400 report found is from March 2026.
2. Whether, under adaptive thinking, Claude thinks on the request that follows a harness-written tool call. The docs say only that such requests "can skip thinking".
3. Whether a user message that holds a tool result plus new text starts a new turn for Anthropic's manual-mode check. For Gemini, the Vertex wording ("the most recent user message that is not a `functionResponse`") does not say how a message with both parts is treated.
4. When Anthropic introduced the silent downgrade. No release note entry for it was found.
5. Whether the adaptive-mode relaxation is the same on Amazon Bedrock, Vertex AI and Microsoft Foundry. The pages read do not list platform differences for it.
6. Whether Anthropic requires the tool named in a harness-written `tool_use` block to be present in `tools`.
7. What OpenRouter does for a Claude model in manual thinking mode when the current turn's tool call has no `reasoning_details`.
8. Whether a dummy Gemini signature can be passed through OpenRouter.
9. How the Gemini Interactions API treats a function call step that the model did not produce.
10. Whether the Gemini 3 rules apply unchanged to Gemini 4 Argon. The Vertex page speaks of "Gemini 3 models".
11. A primary OpenAI statement that a function call item without a response item id needs no reasoning item.
12. Which OpenAI models "newer frontier models" refers to in "Keep the prefix unchanged".
13. Primary documentation for DeepSeek, Qwen, Mistral, MiniMax and Z.ai. The DeepSeek docs host timed out and the others were not read.
14. Any issue or doc about Google ADK `before_model_callback` returning a function call, LangChain `jump_to: "tools"`, the Vercel AI SDK or the OpenAI Agents SDK that covers a harness-written call together with a thinking model.

## Access notes

- `platform.claude.com`, `openrouter.ai`, `docs.litellm.ai`, `pypi.org` and `raw.githubusercontent.com` were read directly.
- `ai.google.dev`, `aistudio.google.com`, `platform.openai.com`, `developers.openai.com`, `api-docs.deepseek.com`, `github.com` and `archive.org` could not be reached directly. Pages on those hosts were read through search and fetch services, so quotes from them were not checked against the live page byte for byte.
- GitHub issues and pull requests were read as search excerpts, not in full.
