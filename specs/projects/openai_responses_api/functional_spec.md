---
status: complete
---

# Functional Spec: OpenAI Responses API for newer OpenAI models

## Purpose

Let users attach tools to Kiln's newer OpenAI-direct models (GPT-5.4 and later, GPT-6 and later) and optionally see their reasoning. We do this by upgrading LiteLLM, which already routes these calls to OpenAI's `/v1/responses`, and by fixing the defaults and model-list entries around it. See the [project overview](./project_overview.md) and the [research summary](../../research/openai-responses-api/summary.md).

Kiln's public interface does not change. `invoke`, `invoke_returning_run_output`, `invoke_openai_stream`, `invoke_ai_sdk_stream`, `TaskRun.trace` and `prior_trace` keep their current types and formats.

## Affected models

All of the models below are on the **OpenAI provider only** (`ModelProviderName.openai`). The same models on OpenRouter, and every other provider, are unchanged.

| Group | Providers (model ids) |
|---|---|
| Tools currently off (the "ten") | `gpt-5.4`, `gpt-5.5`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6.1-sol`, `gpt-6.1-terra` |
| Already on Responses today | `gpt-5.4-pro`, `gpt-5.2-pro` (LiteLLM's model map marks them Responses-only) |

## Delivery: two branches

Turning tools on reaches every installed app through the remote model list, including old versions that lack the new LiteLLM. So the work ships on two branches:

- **Branch 1 — code, plus the one model-list change the release needs.** Merged to `main` and shipped in the next app release. Contains F1, F2, F5 and the branch-1 part of F7 below. F5 includes the new `openai_reasoning_summary` provider field and its values on the twelve providers. That model-list change is safe for old apps, because they ignore fields they don't know. The released app needs it in the published remote model list, not only in its bundled one: at startup the app replaces its bundled list with the published list, without merging. So the field is published by a push to `remote_config` after branch 1 merges, before or with the release.
- **Branch 2 — every other model-list change.** Built on branch 1. Merged to `main` only **after** the release with branch 1 is live, then published by pushing to the `remote_config` branch. Contains F3, F4, F6 and the rest of F7.

Merging to `main` does not publish the remote model list; only a push to `remote_config` does. The release checklist has two pushes. The first follows the branch 1 merge and goes out before or with the release. The second follows the branch 2 merge. The branch 2 merge and the second push both wait until the release is out.

## Features

### F1. Upgrade LiteLLM (branch 1)

- Move the `litellm` requirement in `libs/core/pyproject.toml` from `>=1.102.0,<1.103` to the newest 1.105.x that passes the repo's 7-day PyPI cooldown (1.105.6 as of 2026-11-03), keeping the tight-range policy: `>=1.105.6,<1.106`. Update `uv.lock` with the repo's tooling.
- Why this version: 1.103.5 fixed the bug where a reply containing both text and a tool call came back as two choices and Kiln lost the tool call; 1.105.6 has the fix (checked against a local fake server). Not 1.106.x: from 1.106.0, LiteLLM loads `mcp>=2.2` on every tool call, and Kiln is on `mcp` 1.x, so every tool call would fail. 1.106.0's other fix, for invented reasoning ids, doesn't affect Kiln. See [architecture §1](./architecture.md).
- The upgrade spans four minor versions and affects all 200+ models. All unit tests must pass, and the team runs the full paid suite across all providers before branch 1 merges (see Testing). Any regression found is fixed in branch 1 or reported to the user before merge.

### F2. Don't let OpenAI store requests (branch 1)

- Every call the LiteLLM adapter makes to the OpenAI provider sends `store: false`. That covers Chat Completions and Responses alike, because Kiln can't know in advance which endpoint LiteLLM will choose.
- Not affected: OpenRouter, Azure OpenAI, OpenAI-compatible custom providers, the document extractor, embeddings and rerankers.
- Why: Responses keeps every request for at least 30 days by default and shows it in the OpenAI dashboard; Chat Completions' reference says its default is not to store. Moving calls to Responses would otherwise change retention without anyone choosing it. `store: false` also gives Zero Data Retention organizations, which OpenAI forces to `store: false`, the same behavior as everyone else.
- The tool loop must keep working with `store: false`. Within one run, LiteLLM sends the model's encrypted reasoning back between tool rounds; OpenAI returns that encrypted copy by default when `store` is false. A paid test confirms it (see Testing).

### F3. Turn tools on for the ten models (branch 2)

- Remove `supports_function_calling=False` and its workaround comment from the ten providers in `ml_model_list.py`.
- Behavior after the change, with branch 1's LiteLLM:

| Run | Endpoint LiteLLM uses |
|---|---|
| Tools attached, thinking level other than `none` | `/v1/responses` |
| Tools attached, thinking level `none` | `/v1/chat/completions` (see F6) |
| No tools, summaries off | `/v1/chat/completions` (unchanged from today) |
| Summaries on (any tools, any level) | `/v1/responses` |

- Every existing feature that offers tools for a model starts offering them for these ten: run configs, the model picker, fine-tune tool support.
- No existing run config changes, because none can have tools on these models today.

### F4. Hide `max` on GPT-6 Astra, Sol and Luna (branch 2)

- Remove the `max` thinking level from the OpenAI-direct providers for `gpt-6-astra`, `gpt-6-sol` and `gpt-6-luna`. The OpenRouter providers for these models, and other models that share the same level lists, keep `max`.
- Add a comment in `ml_model_list.py` at the new level lists explaining why. It must say: `/v1/chat/completions` rejects `max` for these models with a 400; only `/v1/responses` accepts it; LiteLLM sends a call to Responses only when tools are attached (or summaries are on), so a run at `max` without tools would fail; restore `max` once every call to these models goes to Responses. GPT-6.1 Sol and Terra already hide `max` for the same reason, so their comment should match.
- Existing run configs saved at `max` on these three providers are left alone. They fail today without tools and keep failing; no migration.

### F5. Reasoning summaries setting (branch 1)

**What it does.** When on, Kiln asks OpenAI for a summary of the model's reasoning on the affected models, and shows it as the run's reasoning, the same way it shows reasoning from other providers. When off (the default), nothing changes from today.

**Which models: a per-provider field.**
- A new optional field on `KilnModelProvider`, `openai_reasoning_summary: str | None`, default `None`. It follows the pattern of `anthropic_summarized_thinking`. The name matches OpenAI's `reasoning.summary` parameter and LiteLLM's `reasoning_summary` argument.
- Its value is the summary mode Kiln sends, passed through as-is. It is a plain string, not an enum, so a summary mode OpenAI adds later can go into the model list without a client release.
- It is set to `"auto"` on the twelve OpenAI-direct providers in the table above: the ten plus `gpt-5.4-pro` and `gpt-5.2-pro`. It is `None` everywhere else.
- Kiln sends `reasoning_summary=<value>` only when the field is set **and** the user's setting is on. When the setting is off, the field has no effect.

**Where the setting lives.**
- A checkbox, off by default, in the OpenAI API-key dialog on the connect-providers screen. It appears both in onboarding and in Settings → Providers, because they share that dialog.
- Next to it is an (i) info tooltip. The tooltip says that summaries show the model's reasoning in Kiln, and that OpenAI requires organization verification for them (with unverified orgs, runs on these models fail). It links to OpenAI's organization settings page.
- The setting is chosen when the user connects OpenAI. To change it later, the user disconnects OpenAI and connects again. The checkbox always starts unchecked, because the dialog only opens while OpenAI is disconnected and disconnecting turns the setting off. This means existing users have to re-enter their key to turn it on. That cost is accepted.
- Disconnecting OpenAI turns the setting off.
- Users who connected before this release start with it off.
- It is a global Kiln setting stored with the OpenAI key, not per project or per run config.

**Where it applies.** Every run on a qualifying provider through the LiteLLM adapter: task runs, evals and judges, data generation, synthetic users, repair and chat. Not the document extractor.

**How reasoning appears.**
- It is saved in the run's intermediate outputs as `reasoning`, like other reasoning models, and shown wherever Kiln shows reasoning today.
- A summary can arrive in several parts. The saved reasoning contains every part, in order, separated by a blank line. It is the same text whether the run was streamed or not.
- When streaming, all parts appear in the reasoning stream in order. None go missing or onto a different stream.
- A run at thinking level `none`, or a reply where OpenAI returns no summary, has no reasoning. That is not an error.

**When the org isn't verified.** OpenAI rejects the request with HTTP 400 and the message "Your organization must be verified to generate reasoning summaries…". Kiln currently turns every unrecognized LiteLLM error into "An unexpected error occurred.", so OpenAI's message would never reach the user. Kiln recognizes this one error and shows: "Your OpenAI organization must be verified to show reasoning summaries. Verify it in your OpenAI organization settings (https://platform.openai.com/settings/organization/general), or disconnect OpenAI in Kiln settings and reconnect with reasoning summaries turned off." The run fails; there is no silent retry. Other errors are unchanged.

### F6. Check GPT-6.1 Terra with tools at `none` (branch 2)

- OpenAI's docs say GPT-6.1 Terra needs Responses for any tool use, but LiteLLM keeps tools at `none` on Chat Completions. One paid call checks it.
- If it fails, remove `none` from GPT-6.1 Terra's OpenAI-direct thinking levels on branch 2, with a comment saying why. Its default level is `medium`, so the default doesn't change.
- If the paid suite finds tools failing at `none` on any other of the ten models, stop and report to the user instead of removing the level. GPT-5.4's default level is `none`, so removing it there would change defaults. OpenAI rejected tools at `none` on GPT-5.4 in April 2026 (#1351), and its docs now say it is allowed. This must be tested before branch 2 ships.

### F7. Update maintainer docs (both branches)

- Update `.agents/skills/claude-maintain-models/SKILL.md` so new OpenAI-direct models are no longer added with `supports_function_calling=False`, and explain when `max` must be hidden. This part goes on branch 2.
- Document the `openai_reasoning_summary` field in the same skill: which OpenAI-direct providers should set it (GPT-5.4+ and GPT-6+ reasoning models), and that the value is passed to OpenAI as-is. This part goes on **branch 1**, with the field, so models added before branch 2 merges get it.
- Run the repo's docs-sync skill for any other docs the change makes stale.

## Rollout

1. Branch 1 merges after its tests and the full paid suite pass.
2. Someone pushes to `remote_config`, before the app release or with it. The published model list then carries `openai_reasoning_summary`, which old apps ignore. If the release ships first, new apps replace their bundled list with the older published one at startup, and turning on summaries has no effect until this push.
3. The app release with branch 1 ships. New apps send `store: false`, offer the summaries setting, and have the fixed LiteLLM. The model list still has tools off on the ten models.
4. Branch 2 merges to `main`.
5. Someone pushes to `remote_config` again. All apps, old and new, receive tools on (and hidden `max`) on their next startup.

**Accepted risk for old apps.** An old app that receives the new model list lets users attach tools to the ten models without the fixed LiteLLM:
- On GPT-6 models (Astra, Sol, Luna, 6.1 Sol, 6.1 Terra), old apps on LiteLLM 1.87.1 get OpenAI's 400 error.
- On GPT-5.4 to 5.6, they can silently lose tool calls when a reply has text and a tool call together.

Old apps already show an upgrade prompt. No existing run config is affected.

## Testing

- **Unit tests** for each change: the `store` default, summaries on and off per provider, the multi-part summary join (streamed and not), the unverified-org error message, and the model-list changes. Offline wire tests that check request bodies sent to `/v1/responses` use the existing `respx` pattern from the Cloudflare tests. Watch for tests that build bare `Mock()` providers, which read any new boolean field as true.
- **Paid tests (new):**
  - tools at every thinking level on the ten models;
  - a reply with narration plus a tool call (the old lost-tool-call case);
  - a tool loop with `store: false`;
  - summaries on, with a verified org, streamed and not;
  - the ten models added to the paid streaming and `return_on_tool_call` test lists.
- **Who runs the paid tests.** The coding agent writes the tests and the exact commands; someone on the team runs them locally with real keys, because this environment has none. Branch 1: the full paid suite across all providers (for the LiteLLM upgrade). Branch 2: the OpenAI paid tests with tools on, including the F6 check.

## Out of scope

- Keeping reasoning across turns: saved conversations, `return_on_tool_call` resume, and reasoning lost between tool rounds when streaming. A separate project; see [the handoff prompt](../../research/openai-responses-api/handoff_reasoning_across_turns.md).
- Routing tool-less `max` calls to Responses.
- A native `litellm.aresponses()` path or a Kiln provider routing flag.
- Azure OpenAI, OpenRouter, and OpenAI models other than the twelve above.
- Migrating saved run configs.
