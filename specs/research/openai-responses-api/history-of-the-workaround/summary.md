# History of the workaround

## Bottom Line

`supports_function_calling=False` was added on 2026-04-30 in [#1351](https://github.com/Kiln-AI/Kiln/pull/1351) for gpt-5.4 and gpt-5.5. At that time it was the right call: Kiln's locked LiteLLM 1.81.16 sent every tools-plus-reasoning call to `/v1/chat/completions`, and OpenAI answered with a 400. Every later GPT model on OpenAI direct copied the flag. Ten providers have it today: gpt-5.4, gpt-5.5, gpt-5.6-sol/terra/luna, gpt-6-astra/sol/luna, gpt-6.1-sol/terra.

Two LiteLLM bumps made for other reasons made the flag stale without anyone noticing. 1.87.1 (2026-06-18) began routing gpt-5.4+ tool calls to `/v1/responses` on its own. 1.102.0 (2026-09-30) extended that to gpt-6*. On `main` today, a tool call at any level except `"none"` goes to `/v1/responses` for all ten ids, so removing the flag would not bring back the 400.

The real bug today is what LiteLLM's automatic conversion does once it routes a call. A turn with text plus a tool call loses the call silently. Structured output is sent with `strict: false`. No reasoning summary is requested. `store` is left at OpenAI's default, and reasoning is replayed by id. Kiln already runs this path in production for gpt-5.4-pro and gpt-5.2-pro, with tools on.

The flag also cannot simply be removed from the remote model list. The latest released desktop build, v1.2.0, ships LiteLLM 1.87.1, which does not route `gpt-6*` and would hit the 400.

## Key Findings

- **Origin was a real 400 with no LiteLLM help.** #1351 (merged 2026-04-30, LiteLLM 1.81.16): "OpenAI rejects reasoning_effort + tools on /v1/chat/completions for GPT-5.4+ with a 400. Even default_thinking_level="none" sends reasoning_effort: "none", which trips the same check." The same gpt-5.4 tools test at the default `"none"` had passed on 2026-03-11 ([#1103](https://github.com/Kiln-AI/Kiln/pull/1103)), so OpenAI's behavior changed in between. — [timeline.md](./timeline.md)
- **Each LiteLLM version, read from source.** 1.81.16 has no automatic rule. 1.87.1 bridges `gpt-5.4+` names when tools are present and any effort is set, including `"none"`, but not `gpt-6*`. 1.102.0 bridges `gpt-5.4+` and `gpt-6*` when tools are present and the effort is not `"none"`. These are the `responses_api_bridge_check` and `OpenAIGPT5Config` sources of each version. — [timeline.md](./timeline.md)
- **The flag became stale at different times.** gpt-5.4 and 5.5 since 2026-06-18. gpt-5.6-* and gpt-6.1-* from the day they were added. gpt-6-astra/sol/luna since 2026-09-30. Neither bump PR ([#1480](https://github.com/Kiln-AI/Kiln/pull/1480), [#1829](https://github.com/Kiln-AI/Kiln/pull/1829)) mentions OpenAI. — [timeline.md](./timeline.md)
- **OpenAI's exact error never appears in Kiln PRs, tests or fixtures.** Public reports give two wordings. March 2026: "Function tools with reasoning_effort are not supported for gpt-5.4 in /v1/chat/completions. Please use /v1/responses instead." ([pipecat #4043](https://github.com/pipecat-ai/pipecat/issues/4043)). Later: "... for gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'." ([OpenAI forum](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454)). OpenAI's migration guide: "Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`." — [openai-error-messages.md](./openai-error-messages.md)
- **Today's routing, measured with Kiln's real adapter against a local fake server.** All ten ids go to `/v1/responses` at non-`none` levels, and the tool loop completes. `"none"` stays on chat. Tool-less calls stay on chat for all ten. Because of the defaults, gpt-5.4, gpt-5.5, gpt-5.6-sol and gpt-5.6-luna would use chat at their default level and responses at any other level. — [current-state.md](./current-state.md)
- **What breaks if the flag is removed today.** A narration-plus-function-call reply produces `tool called with: []` and the final output `'Let me add those numbers.'`, with no error. `text.format` is sent as `{"type": "json_schema", ..., "strict": false}`. A custom `temperature`/`top_p` is silently dropped. There is no `store`, `include` or `reasoning.summary`. Older clients on LiteLLM 1.87.1 would get 400s for `gpt-6*`. — [current-state.md](./current-state.md)
- **Pro models already use the conversion.** LiteLLM's model map marks `gpt-5.4-pro` and `gpt-5.2-pro` `mode: responses`, so every Kiln call to them goes through it, with tools enabled. The GPT-6 Pro variants are OpenRouter-only in Kiln, because OpenAI direct returns "model does not exist" for those ids ([#1894](https://github.com/Kiln-AI/Kiln/pull/1894)). — [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md)
- **Other workarounds caused by Chat Completions.**
  - `max` is hidden on GPT-6.1 Sol and 6.1 Terra because chat returns a 400 for it.
  - `max` is still offered on GPT-6 Astra, Sol and Luna even though chat returns a 400 for it. That is a live bug; the fix, [#1831](https://github.com/Kiln-AI/Kiln/pull/1831), was closed unmerged.
  - There is no reasoning text on OpenAI direct ("0 of 61 live cases", [#1806](https://github.com/Kiln-AI/Kiln/pull/1806)), and the paid test fails by design ([#1562](https://github.com/Kiln-AI/Kiln/pull/1562) closed unmerged).
  - GPT-6 rejected `temperature != 1` with a 400 on LiteLLM 1.87.1. LiteLLM 1.102.0 now drops it silently.
  - Routing only tool calls would not unlock `max` or reasoning summaries for tool-less runs. — [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md)
- **Closed PR #1757's version claims check out against source.** It said "litellm 1.87.1 already sends the gpt-5.x names to `/v1/responses` when the request has tools and a reasoning effort" and that gpt-6-astra is outside that check; both are correct. Its split-choice and `strict: false` findings, made on 1.87.1, still reproduce on 1.102.0. — [timeline.md](./timeline.md), [current-state.md](./current-state.md)

## Details

- [timeline.md](./timeline.md) — Dated step-by-step history: each PR, the providers it touched, the LiteLLM lock on `main` at the time, the routing code in each LiteLLM version, release tags and their LiteLLM version, and a per-provider table of when the flag went stale. Read this for "when and why".
- [current-state.md](./current-state.md) — Method and outputs of the static routing probe and the fake-server runs on LiteLLM 1.102.0. Includes the per-model endpoint table by thinking level and the numbered list of what breaks if the flag is removed. Read this before deciding whether to rely on LiteLLM's automatic routing.
- [openai-error-messages.md](./openai-error-messages.md) — Verbatim error texts: tools plus effort (two wordings, with dates), `max` (Kiln probes), `temperature`, Pro ids. Also OpenAI's doc statements and the open question about `"none"`.
- [other-chat-completions-workarounds.md](./other-chat-completions-workarounds.md) — Hidden and still-exposed `max`, missing reasoning text, temperature/top_p, Pro models, OpenRouter's reasoning object, and LiteLLM 1.81.16 silently dropping `xhigh`.

## Open Questions / Gaps

- **No live OpenAI calls.** `OPENAI_API_KEY` is not set, so no paid calls were made. The fake server shows what Kiln and LiteLLM put on the wire, not how OpenAI answers. In particular, it is unverified whether OpenAI **today** accepts `reasoning_effort: "none"` plus tools on gpt-5.4 / gpt-5.5 on chat. #1351 saw it rejected on 2026-04-28, while current OpenAI docs and the later error text say `"none"` is allowed.
- **Why #1562 and #1757 were closed.** Neither PR has a closing comment, and #1831 has none either. The reason may be in Slack or Linear (KIL-618, referenced by #1757), which are not reachable from here.
- **LiteLLM's live map at the time of #1351.** I could not read LiteLLM's live model map as of April 2026. The GitHub API for BerriAI/litellm is blocked in this session. So it is not proven why `gpt-5.4-pro` passed the tools test then. The likely reason is `mode: responses` in the live map, since the bundled 1.81.16 map lacks the entry.
- **Not tested here.** The streaming paths (`invoke_openai_stream`, `invoke_ai_sdk_stream`) through the bridge, and multi-turn replay of bridged turns from `prior_trace`. Both are left to the LiteLLM and adapter subtopics.
- **What exactly changed in OpenAI's behavior.** The March→April 2026 change for `"none"` is inferred from Kiln test results and LiteLLM's rule history, not from an OpenAI announcement.

## Sources

- Kiln git history, `origin/main` deepened to 2025-12-01. `git log -S` on the workaround comment; `git show <commit>:uv.lock` for each lock; release tags v0.27.1 – v1.2.0.
- Kiln PRs (read via GitHub MCP, 2026-10-30):
  - [#1103](https://github.com/Kiln-AI/Kiln/pull/1103) — GPT-5.4 added, tools pass (2026-03-11)
  - [#1351](https://github.com/Kiln-AI/Kiln/pull/1351) — workaround introduced (2026-04-30)
  - [#1480](https://github.com/Kiln-AI/Kiln/pull/1480) — LiteLLM 1.87.1 (2026-06-17)
  - [#1560](https://github.com/Kiln-AI/Kiln/pull/1560) — GPT-5.6, `max` error (2026-07-14)
  - [#1562](https://github.com/Kiln-AI/Kiln/pull/1562) — reasoning summaries, closed
  - [#1755](https://github.com/Kiln-AI/Kiln/pull/1755) — GPT-6 Astra (2026-09-08)
  - [#1757](https://github.com/Kiln-AI/Kiln/pull/1757) — routing attempt, closed (branch `mike/openai-responses-routing` read locally)
  - [#1806](https://github.com/Kiln-AI/Kiln/pull/1806) — GPT-6 Sol/Luna, temperature 400 (2026-09-23)
  - [#1829](https://github.com/Kiln-AI/Kiln/pull/1829) — LiteLLM 1.102 (2026-09-29)
  - [#1830](https://github.com/Kiln-AI/Kiln/pull/1830) — GPT-6.1 Sol (2026-10-01)
  - [#1831](https://github.com/Kiln-AI/Kiln/pull/1831) — `max` probe, closed
  - [#1894](https://github.com/Kiln-AI/Kiln/pull/1894) — GPT-6 Pro on OpenRouter only (2026-10-05)
  - [#1982](https://github.com/Kiln-AI/Kiln/pull/1982) — GPT-6.1 Terra (2026-10-28)
- LiteLLM source: 1.102.0 installed at `.venv/lib/python3.13/site-packages/litellm/` (`main.py` `responses_api_bridge_check`, `llms/openai/chat/gpt_5_transformation.py`, `llms/openai/responses/transformation.py`). Also the [1.81.16 wheel](https://files.pythonhosted.org/packages/1f/1e/0022cde913bac87a493e4a182b8768f75e7ae90b64d4e11acb009b18311f/litellm-1.81.16-py3-none-any.whl) and the [1.87.1 wheel](https://files.pythonhosted.org/packages/ff/18/8275c95ef09e81ab0c01a162c7b780ce3fbc49066b5d532c6b6ab3dc0118/litellm-1.87.1-py3-none-any.whl) from PyPI, read only.
- [OpenAI: Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses) and [OpenAI: Reasoning models](https://developers.openai.com/api/docs/guides/reasoning) — the GPT-5.4+ tools rule, GPT-6 Astra / 6.1 Sol Responses-only tool calling, `store` defaults. Fetched 2026-10-30.
- [OpenAI Developer Community: Gpt-5.6 chat completion reasoning effort](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454) — later error wording, OpenAI staff reply.
- [pipecat #4043](https://github.com/pipecat-ai/pipecat/issues/4043) (2026-03-16), [BerriAI/litellm #23156](https://github.com/BerriAI/litellm/issues/23156) (2026-03-09), [open-webui #22343](https://github.com/open-webui/open-webui/issues/22343) (2026-03-07), [pydantic-ai #4667](https://github.com/pydantic/pydantic-ai/issues/4667) (2026-03-15), [Frigate discussion #24555](https://github.com/blakeblackshear/frigate/discussions/24555) (2026-10-03) — dated third-party reports of the error text.
- Local experiment scripts and outputs: `/tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/` (`model_map_probe.py`, `fake_openai_server.py`, `drive_kiln_against_fake.py`, `dump_bodies.py`, `structured_probe.py`, `temperature_probe.py`, and their `*_output.txt` / `probe_*.txt` files). These are session scratch files, not committed to the repo.
