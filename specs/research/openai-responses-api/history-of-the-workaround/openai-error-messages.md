# OpenAI error messages behind the Chat Completions workarounds

Kiln's own PRs, tests and fixtures do **not** quote the tools-plus-reasoning error. #1351 only says "a 400". A search of every fetched branch (`git log --all -S "Function tools with reasoning_effort"`) finds nothing. Kiln PRs do quote the `max` error verbatim. The tools error text below comes from public third-party reports and from LiteLLM's source.

## Tools + `reasoning_effort` on `/v1/chat/completions`

Two wordings appear, and they say different things about `"none"`.

**March 2026 wording (gpt-5.4).** It says nothing about `none`:

> `Error code: 400 - {'error': {'message': 'Function tools with reasoning_effort are not supported for gpt-5.4 in /v1/chat/completions. Please use /v1/responses instead.', 'type': 'invalid_request_error', 'param': 'reasoning_effort', 'code': None}}`

Source: pipecat issue [#4043](https://github.com/pipecat-ai/pipecat/issues/4043) (opened 2026-03-16, `reasoning_effort: "low"`). The same text appears in LiteLLM issue [#23156](https://github.com/BerriAI/litellm/issues/23156) (opened 2026-03-09, LiteLLM 1.82.0, `reasoning_effort="low"`), open-webui [#22343](https://github.com/open-webui/open-webui/issues/22343) (2026-03-07), and alibaba/page-agent PR [#169](https://github.com/alibaba/page-agent/pull/169) (2026-03-08). pydantic-ai issue [#4667](https://github.com/pydantic/pydantic-ai/issues/4667) (2026-03-15) reports the same text for `gpt-5.4-2026-03-05` with an example that sets `"openai_reasoning_effort": "none"`. Unverified: whether pydantic-ai actually put `"none"` on the wire.

**Later wording (gpt-5.6-sol).** It names `none` as an allowed fix:

> `Function tools with reasoning_effort are not supported for gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.`

Source: OpenAI Developer Community thread "[Gpt-5.6 chat completion reasoning effort [bug / behavior change]](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454)". An OpenAI reply in that thread: "Responses supports the tool workflow, but we haven't confirmed a fix for this exact Chat Completions combination." A generic form without the model name ("Function tools with reasoning_effort are not supported in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.") is quoted in github/gh-aw issue [#56676](https://github.com/github/gh-aw/issues/56676).

**LiteLLM's copy.** LiteLLM 1.102.0 quotes the later wording in `litellm/main.py` (`responses_api_bridge_check`): `"Function tools with reasoning_effort are not supported ... use /v1/responses or set reasoning_effort to 'none'"`.

**OpenAI's docs (fetched 2026-10-30).**
- Migration guide, [developers.openai.com/api/docs/guides/migrate-to-responses](https://developers.openai.com/api/docs/guides/migrate-to-responses): "Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`." and "GPT-6 Astra and GPT-6.1 Sol require the Responses API for tool calling."
- Reasoning guide, [developers.openai.com/api/docs/guides/reasoning](https://developers.openai.com/api/docs/guides/reasoning): "Use the Responses API for function calling. Chat Completions does not support function calling with GPT-6 Astra or GPT-6.1 Sol." and "GPT-6 Astra does not support `none` reasoning effort. Setting `reasoning.effort` (Responses) or `reasoning_effort` (Chat Completions) to `none` returns HTTP 400. GPT-6.1 Sol does not support `none` or `minimal` and defaults to `medium`."

**What this means for `"none"` (inference, not verified live).** Kiln's history fits a rule that changed over time:
- 2026-03-11: gpt-5.4 + tools at `"none"` passed in Kiln (#1103).
- 2026-04-28: the same test failed (#1351, "Even default_thinking_level="none" sends reasoning_effort: "none", which trips the same check").
- LiteLLM 1.87.1 bridged any explicit effort, including `"none"`. LiteLLM 1.102.0 keeps `"none"` on chat.
- Today's OpenAI docs and the later error text both say `"none"` is allowed.

Whether `"none"` plus tools on gpt-5.4 / gpt-5.5 is accepted by OpenAI **today** could not be checked without an API key. See the open questions in [summary.md](./summary.md).

## Unset effort on GPT-6 models

A Frigate maintainer, 2026-10-03, discussion [#24555](https://github.com/blakeblackshear/frigate/discussions/24555): "Frigate doesn't send `reasoning_effort` to OpenAI unless you specify it, and these newer models reason by default. OpenAI doesn't allow reasoning together with tools on the chat completions endpoint." LiteLLM 1.102.0 handles this with the "unset effort" branch of its rule (bridge when the host is api.openai.com). That branch does not apply to Kiln, which always sends an explicit effort for these providers. LiteLLM's issue tracker links it to PR #33237, "fix(openai): bridge gpt-5.6+ with tools to /v1/responses even without reasoning_effort" (seen in the [#23156](https://github.com/BerriAI/litellm/issues/23156) timeline; not read further, since it belongs to the LiteLLM subtopic).

## `max` reasoning effort on `/v1/chat/completions`

Quoted verbatim in Kiln PRs:

- GPT-5.6 Sol, PR [#1560](https://github.com/Kiln-AI/Kiln/pull/1560) (2026-07): `400 - 'reasoning_effort' does not support 'max' with this model. Supported values are: 'none', 'low', 'medium', 'high', 'xhigh'` ("deterministically on both providers").
- GPT-6 family, PR [#1831](https://github.com/Kiln-AI/Kiln/pull/1831), "Direct API probe, 2026-09-29":
  ```
  gpt-6-astra max -> 400 Unsupported value: 'reasoning_effort' does not support 'max' with this model. Supported values are: 'low', 'medium', 'high', and 'xhigh'.
  gpt-6-sol   max -> 400 Unsupported value: 'reasoning_effort' does not support 'max' with this model. Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'.
  gpt-6-luna  max -> 400 Unsupported value: 'reasoning_effort' does not support 'max' with this model. Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'.
  gpt-6-astra xhigh -> 200
  gpt-6-luna  xhigh -> 200
  gpt-6-luna  none  -> 200
  gpt-6-sol   none  -> 200
  ```
- GPT-6.1 Sol, PR [#1830](https://github.com/Kiln-AI/Kiln/pull/1830): chat rejects `max` with a 400 (`Supported values are: 'low', 'medium', 'high', and 'xhigh'`), "while `/v1/responses` accepts it".
- GPT-6.1 Terra, PR [#1982](https://github.com/Kiln-AI/Kiln/pull/1982): "a 400 naming exactly those five values for `max`, `minimal` and a made-up value". No verbatim string.

## `temperature` on GPT-6 (OpenAI direct)

PR [#1806](https://github.com/Kiln-AI/Kiln/pull/1806) (2026-09-23, LiteLLM 1.87.1): "at `temperature=0` every GPT-6 request was rejected with a 400 before reaching the model". No verbatim string. The paid test now hard-codes `temperature = 1` with the comment "Anthropic requires temperature 1 with thinking on, and GPT-6 rejects any other" (`libs/core/kiln_ai/adapters/model_adapters/test_thinking_level_paid.py`). Under LiteLLM 1.102.0 the 400 no longer happens: LiteLLM drops the parameter instead (see [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md)).

## GPT-6 Pro ids on OpenAI direct

PR [#1894](https://github.com/Kiln-AI/Kiln/pull/1894) (2026-10-05): "a live call to each id on both `/v1/chat/completions` and `/v1/responses` returns "model does not exist". On OpenAI, Pro is a request parameter, not a model id." No verbatim body.
