---
status: complete
---

# Phase 1: Upgrade LiteLLM to 1.105.6 and send `store: false`

## Overview

Move LiteLLM from 1.102 to 1.105.6, which fixes the lost tool call when a reply has text and a tool call together, and stays below 1.106.0, which breaks every tool call by importing `mcp` 2.x. Then make every LiteLLM adapter call to the OpenAI provider send `store: false`, so calls that LiteLLM routes to `/v1/responses` aren't kept by OpenAI for 30 days. Add offline wire tests that run real LiteLLM against `respx`, and one paid test for a `store: false` tool loop.

This phase changes no model-list entries and adds no setting.

## Steps

1. **Pin LiteLLM.** In `libs/core/pyproject.toml`, replace `"litellm>=1.102.0,<1.103",` with `"litellm>=1.105.6,<1.106",`. Directly above it, add a two-line comment: LiteLLM 1.106.0+ imports `mcp>=2.2` (an optional LiteLLM extra) on every tool call, and Kiln is on `mcp` 1.x, so raise the cap only together with an `mcp` 2.x upgrade.
   - 1.105.7 was published 2026-10-28 22:50 UTC, which is inside the 7-day cooldown at implementation time, so 1.105.6 stays the target.

2. **Lock.** Run `uv lock --upgrade-package "litellm==1.105.6"` from the repo root, then `uv sync`. Don't edit `uv.lock` by hand. Expect `boto3`/`botocore`, `certifi`, `pyyaml` and `tiktoken` to move and `h2`, `hpack`, `hyperframe` to appear. Confirm `mcp` stays on 1.x.

3. **Send `store: false`.** In `LiteLlmAdapter.build_extra_body` (`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`), add before the `provider_options` merge:

   ```python
   if provider.name == ModelProviderName.openai:
       # Responses stores requests for 30 days by default; Kiln opts out on both endpoints.
       extra_body["store"] = False
   ```

   The provider-name check covers OpenAI fine-tunes too (they are named `openai`) and excludes OpenRouter, Azure OpenAI and OpenAI-compatible providers.

4. **Fix existing tests** that assert an exact `extra_body` or completion kwargs for an OpenAI provider, if the new key breaks them.

5. **Wire tests.** New `libs/core/kiln_ai/adapters/model_adapters/test_openai_responses_wire.py`, following `test_cloudflare_litellm.py`:
   - autouse fixture sets `litellm.disable_aiohttp_transport = True`;
   - the OpenAI key is set with `Config.shared().open_ai_api_key = ...` on the temp settings file from the root `conftest.py`, not with a `Config` patch;
   - `respx` mocks `POST https://api.openai.com/v1/responses` with canned Responses bodies (reasoning item, optional message, function call; then a final message);
   - the adapter is built with `adapter_for_task` for `gpt_5_4_pro` on `ModelProviderName.openai` at `medium`, with `available_tools` patched to `[AddTool()]`.

6. **Paid test.** In `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py`, add `test_tools_store_false_gpt_5_4_pro`: run the two-round math tool loop (`run_simple_task_with_tools`, not simplified) on `gpt_5_4_pro` / OpenAI, with `litellm.acompletion` wrapped by a spy, and assert every call carried `store=False`.

7. **Checks.** Run `uv run ./checks.sh --agent-mode` and the conventions gate on the worktree.

## Tests

- `test_build_extra_body_store_false_only_for_openai` (parametrized, in `test_litellm_adapter.py`): `store` is `False` for `ModelProviderName.openai` and absent for `openrouter`, `azure_openai` and `openai_compatible`. Providers are built with `KilnModelProvider(...)`, not `Mock()`.
- `test_tool_call_on_bridged_model_completes` (wire case 1): a `gpt_5_4_pro` run with one function call and a final message finishes, calls `add(2, 2)`, and returns the final text. This is the dependency smoke test: it fails if LiteLLM can't make a tool call at all (for example, the `mcp` import error in 1.106.x).
- `test_bridged_requests_go_to_responses_with_store_false` (wire case 2): both requests of that loop go to `/v1/responses`, and each body has `"store": false`.
- `test_reply_with_text_and_tool_call_runs_tool` (wire case 4): a first reply that has a message and a function call still runs the tool, and the trace's assistant message has both the text and the tool call.
- `test_tools_store_false_gpt_5_4_pro` (paid): the two-round tool loop on real OpenAI succeeds with `store: false` on every call.

Paid-test command for the team (real OpenAI key):

```
uv run python3 -m pytest --runpaid -q libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py::test_tools_store_false_gpt_5_4_pro
```

Because LiteLLM moves four minor versions, the team also runs the full paid suite across all providers before branch 1 merges:

```
uv run python3 -m pytest --runpaid --ollama -q -n auto libs/core
```
