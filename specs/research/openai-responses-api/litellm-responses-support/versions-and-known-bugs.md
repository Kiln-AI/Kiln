# Versions: what 1.102.x has vs later, and known bugs

## Version landscape (PyPI, checked 2026-10-05)

- Kiln pins `litellm>=1.102.0,<1.103`. The installed version is **1.102.0** (built 2026-09-20 per PyPI). The newest version allowed by the pin is **1.102.2** (2026-09-29).
- The latest stable is **1.104.0** (2026-10-03). 1.105.0rc1 came out on 2026-10-04.
- LiteLLM wheels are now maturin-built, platform-specific (`cp310-abi3-manylinux_2_28_x86_64`; `WHEEL: Generator: maturin (1.9.4)`), and ship a Rust component (`LITELLM_RUST=1` is mentioned in the 1.103 notes). The Python sources are still included, so they can be read and diffed.

## Diffs of the Responses-relevant files (I downloaded the wheels and diffed them)

| File | 1.102.0 → 1.102.2 | 1.102.0 → 1.104.0 |
|---|---|---|
| `main.py` (incl. `responses_api_bridge_check`) | identical | changed |
| `completion_extras/litellm_responses_transformation/transformation.py` | identical | 75 lines |
| `completion_extras/.../handler.py` | identical | typing only |
| `llms/openai/chat/gpt_5_transformation.py` | identical | 37 lines |
| `responses/main.py` | identical | 208 lines |
| `llms/openai/responses/transformation.py` | identical | 36 lines |

**Moving within the current pin (1.102.0 → 1.102.2) changes nothing in the Responses or bridge code.**

Behaviour changes in 1.104.0 that matter here:
- **`verbosity` is mapped to `text.verbosity` on the bridge.** 1.102 drops it silently. The new code is `elif key == "verbosity": responses_api_request["text"] = self._merge_text(...)`, and `response_format` is merged into the same `text` object instead of overwriting it.
- **Non-enum `reasoning_effort` strings are forwarded** on the bridge instead of becoming `reasoning=None` (PR #42452).
- **Azure AI Foundry (`azure_ai`) gets the auto-route.** It uses different boundaries, quoted from the code: "an explicit effort with function tools is rejected from gpt-5.6 on, and the unset effort only from gpt-6 on" (PR #42041).
- `has_function_tool` now requires a well-formed function tool: `isinstance(tool.get("function"), dict) or "name" in tool`.
- Unchanged in 1.104.0 and 1.105.0rc1: `_convert_response_output_to_choices`, so the two-choice split below is still there; and there is still no logprobs mapping.

1.105.0rc1 bridge diff vs 1.104.0: it only adds `service_tier` propagation on streamed chunks and removes some lint comments.

## When the pieces arrived (release notes)

- `openai/responses/` prefix and `mode: responses` bridging: present well before 1.102. The docs say Responses API support began in "1.63.8+". I did not pin down the exact version for the prefix.
- 1.85.0: "Route `gpt-5.4+` chat-without-tools to the Responses API - PR #27618"; "Normalize chat `tool_choice` for the completions→responses bridge - PR #27634" ([v1.85.0 notes](https://docs.litellm.ai/release_notes/v1.85.0/v1-85-0)). *Note:* in 1.102.0, plain `gpt-5.5` + effort with no tools stays on chat (probe A). So that 1.85 behaviour was narrowed later, or applied only with summary aliases. I did not trace when.
- 1.102.0: "Keep reasoning_effort for mode: responses bridge deployments - PR #40249"; "Keep mid-conversation system messages in input instead of folding them into instructions - PR #40269"; "Echo a named tool_choice in the Responses API shape on the chat-completions bridge - PR #40462"; "Keep provider id and metadata on Responses API bridged chat completions - PR #39981"; "Drop unsupported Responses reasoning parameters when drop_params is enabled - PR #38842"; "Call Fireworks' native Responses API - PR #39826" ([v1.102.0 notes](https://docs.litellm.ai/release_notes/v1.102.0/v1-102-0)).
- 1.103.0: "Translate the reasoning object into a chat-completion reasoning effort - PR #36363"; "Recount tokens when a streamed response completes without usage - PR #41337"; "Announce message item before text events in the chat completions bridge - PR #41564"; "Carry image and video input tokens through the Responses usage bridge - PR #41237"; "Accept and forward verbosity on gpt-5.x chat completions - PR #41509" ([v1.103.0 notes](https://docs.litellm.ai/release_notes/v1.103.0/v1-103-0)).
- 1.104.0: see above, plus "Forward safety_identifier through the chat completion bridge - PR #42193"; "Price terminal Responses stream events from their inner response - PR #42385" ([v1.104.0 notes](https://docs.litellm.ai/release_notes/v1.104.0/v1-104-0)).

## Known bugs relevant to calling OpenAI via the completion→responses bridge

| Issue | State (2026-10-05) | Affects 1.102.0? | Impact |
|---|---|---|---|
| [#43316](https://github.com/BerriAI/litellm/issues/43316): text + tool call returned as two choices | Closed 2026-10-03, close reason not visible | **Yes, reproduced (probe B)**. The code is unchanged through 1.105.0rc1. | `choices[0]` has no `tool_calls`, so tool-call loops miss calls whenever the model writes a preamble. Non-streaming only. |
| [#43620](https://github.com/BerriAI/litellm/issues/43620): only the last reasoning item kept when `stream=False` | Open (reported on v1.102.1) | Yes, by code reading | Multi-turn encrypted reasoning replay is incomplete. |
| [#40654](https://github.com/BerriAI/litellm/issues/40654): bridge drops raw `reasoning_text` | Open | Yes | Only summaries appear in `reasoning_content`. |
| [#36992](https://github.com/BerriAI/litellm/issues/36992): plain chat path streams no reasoning progress (79s of silence) | Open (v1.96.2) | Chat path | A reason to prefer the bridge when streaming long reasoning. |
| [#42765](https://github.com/BerriAI/litellm/issues/42765): tool call ids over 64 chars are copied verbatim | Open | Yes | Only matters if ids come from another provider. |
| [#34978](https://github.com/BerriAI/litellm/issues/34978): tool output always wrapped in a list | Open | Yes (probe P) | OpenAI accepts it. Strict third-party Responses backends may not. |
| [#42955](https://github.com/BerriAI/litellm/issues/42955): streaming fallback replays a delivered tool call | Open | Probably | Only with fallbacks configured. |
| [#43817](https://github.com/BerriAI/litellm/issues/43817): `url_citation` dropped when streaming | Open | Probably | Built-in web search only. |
| [#38511](https://github.com/BerriAI/litellm/issues/38511): the streaming error handler masks the original error on the bridge iterator | Open | Probably | Error messages are harder to diagnose. |
| [#43910](https://github.com/BerriAI/litellm/issues/43910), [#40472](https://github.com/BerriAI/litellm/issues/40472): unsupported `none`/`minimal` forwarded | Open | Yes (probe Y) | Provider 400s that LiteLLM does not catch. |
| [#43708](https://github.com/BerriAI/litellm/issues/43708): Databricks gpt-5.6 tools + effort fail on chat | Open | n/a to Kiln providers | The auto-route only covers `openai`/`azure`. |

Gaps I found myself (no upstream issue located):
- **`logprobs=True` is silently dropped** on the bridge. `top_logprobs` is forwarded, but there is no `include: ["message.output_text.logprobs"]`, and no logprobs come back in `choices[].logprobs` (probe H, plus a grep of the bridge for "logprob" finding nothing).
- **`verbosity` is dropped on the bridge** in 1.102.x (probe Q). Fixed in 1.104.0.
- **Chat function tools without `strict` are sent as `strict: null`** (probes B and S). I have not verified how OpenAI's Responses API treats `null`. That belongs to subtopic 1. *Unverified, from memory:* OpenAI's Responses API defaults function tools to strict mode, unlike Chat Completions. If that is true, the omitted-vs-`null` difference matters.
- **`store` is never set by the bridge**, so OpenAI's server-side default applies. That matters for data retention, and for OpenRouter's Responses endpoint, which rejects `store: true`.
- Doc drift: the OpenAI provider docs still say LiteLLM "drops `reasoning_effort`" for gpt-5.4+ with tools. The code auto-routes to Responses instead.
