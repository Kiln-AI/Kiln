# Model list and remote model list

Scope: `KilnModelProvider` (`adapters/ml_model_list.py`), which OpenAI-direct entries a migration touches, thinking levels hidden because of Chat Completions, and how the remote model list reaches older app versions (`adapters/remote_config.py`). Commit `579014ab`, read 2026-10-30. Lists were produced by importing `built_in_models` in this checkout and printing each OpenAI, Azure and OpenRouter GPT provider, not by reading by eye. Labels: **Read**, **Observed**, **Inference**.

## 1. `KilnModelProvider` ([ml_model_list.py:396-516](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L396))

Read. A pydantic `BaseModel` with no `model_config` override, so unknown keys are **ignored** on validation (pydantic default). Fields relevant here:

| Field | Default | Role today |
|---|---|---|
| `name: ModelProviderName` | required | Provider enum (`openai`, `azure_openai`, `openrouter`, ...). |
| `model_id` | `None` | Bare id for `openai` (e.g. `gpt-5.4`); `get_litellm_provider_info` prefixes `openai/`. |
| `adapter: ModelAdapterId` | `litellm` | `litellm` or `jev`. Added in v1.2.0 (commit `59c14696`, 2026-09-19). |
| `supports_function_calling` | `True` | UI-only gate (see §4). Set `False` on the ten affected providers. |
| `structured_output_mode` | `default` | `json_schema` on all GPT-5.x/6.x OpenAI-direct entries. |
| `reasoning_capable` | `False` | `False` on every OpenAI-direct entry. |
| `supports_logprobs` | `False` | `True` only on GPT-4.1/4.1 mini/4.1 nano/4o/4o mini direct. |
| `available_thinking_levels: dict[str, str]` | `None` | Display label → wire value. The validator requires `default_thinking_level` to be one of the values ([L506-516](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L506)). |
| `default_thinking_level` | `None` | Used when the run config does not set `thinking_level`. |
| `litellm_allowed_openai_params` | `None` | Params forced through LiteLLM's `drop_params`. Not used by any OpenAI-direct entry. |
| `openrouter_reasoning_object` | `False` | OpenRouter-only (validator [L495-504](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L495)). Set on OpenRouter GPT-5.5+/6.x entries with the comment "the bare reasoning_effort param is silently dropped on tool calls for these models". |
| `deprecated` | `False` | |

There is no field today that says which OpenAI endpoint to use. The comment above the provider-specific flags ([L446-448](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L446)) says provider-specific parameters are kept "quite declarative here for now, isolating provider specific logic to this file", which is the existing pattern a routing flag would follow.

## 2. OpenAI-direct providers a migration touches

Observed (from `built_in_models`). `fc` = `supports_function_calling`.

### 2a. The ten entries with function calling switched off for the tools + reasoning conflict

Each carries the comment "OpenAI rejects reasoning_effort + tools on /v1/chat/completions for gpt-5.4+. Disable function calling until Kiln routes these models to /v1/responses."

| Model (`ModelName`) | `model_id` | Line | Thinking levels (direct) | Default | Same model on OpenRouter |
|---|---|---|---|---|---|
| `gpt_6_1_sol` | `gpt-6.1-sol` | [945](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L945) | low, medium, high, xhigh (`max` hidden) | medium | + `max`, fc=True |
| `gpt_6_1_terra` | `gpt-6.1-terra` | [1031](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1031) | none, low, medium, high, xhigh (`max` hidden) | medium | + `max`, fc=True |
| `gpt_6_astra` | `gpt-6-astra` | [1087](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1087) | low, medium, high, xhigh, max | medium | same, fc=True |
| `gpt_6_sol` | `gpt-6-sol` | [1177](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1177) | none … max | medium | same, fc=True |
| `gpt_6_luna` | `gpt-6-luna` | [1268](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1268) | none … max | medium | same, fc=True |
| `gpt_5_6_sol` | `gpt-5.6-sol` | [1325](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1325) | none … xhigh | none | same, fc=True |
| `gpt_5_6_terra` | `gpt-5.6-terra` | [1384](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1384) | none … xhigh | medium | same, fc=True |
| `gpt_5_6_luna` | `gpt-5.6-luna` | [1443](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1443) | none … xhigh | none | same, fc=True |
| `gpt_5_5` | `gpt-5.5` | [1499](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1499) | none … xhigh | none | same, fc=True |
| `gpt_5_4` | `gpt-5.4` | [1600](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1600) | none … xhigh | none | same, fc=True |

All ten: `structured_output_mode=json_schema`, `reasoning_capable=False`, `supports_logprobs=False`, `supports_doc_extraction=True`, multimodal (PDF, TXT, MD, JPG, PNG).

### 2b. Other OpenAI-direct GPT-5.x entries that matter

| Entry | State | Why it matters |
|---|---|---|
| `gpt_5_4_pro` (`gpt-5.4-pro`, [L1553](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1553)), `gpt_5_2_pro` (`gpt-5.2-pro`, [L1774](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1774)) | fc=True, levels medium/high/xhigh | LiteLLM's bundled model map marks them `"mode": "responses"`, and I observed the current adapter sending `gpt-5.4-pro` to `/v1/responses` with no Kiln change. They already run on LiteLLM's chat-to-responses layer, with its defects (see [adapter-request-response-path.md](./adapter-request-response-path.md) §3, §6). |
| `gpt_5_4_mini`, `gpt_5_4_nano` ([L1650](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1650), [L1690](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1690)) | fc=True, **no thinking levels** on OpenAI direct; OpenRouter has none…xhigh | Added this way in #1159 (commit `76cf9cf0`, 2026-03-25) with no comment. Cause not established here (history subtopic). Inference: because no `reasoning_effort` is ever sent, these avoid the tools + reasoning conflict. `gpt_5_4_mini`/`openai` is in the prerelease chat list and the OpenAI prompt-caching and structured-output paid tests. |
| `gpt_5_2_chat`, `gpt_5_3_chat` | no levels direct (OpenRouter has levels for 5.2 chat); 5.3 deprecated | Chat variants. |
| `gpt_5_2`, `gpt_5_1`, `gpt_5`, mini, nano | fc=True with thinking levels | Below the gpt-5.4 line; not part of the reported bug. |
| `gpt_5_chat` (`gpt-5-chat-latest`) | fc=False, deprecated | Unrelated reason (no json_schema, "Oddly"). |
| GPT-6/6.1 Pro models (`gpt_6_1_sol_pro`, `gpt_6_1_terra_pro`, `gpt_6_sol_pro`, `gpt_6_luna_pro`) | **OpenRouter only**, no OpenAI-direct entry | Inference: Pro models are Responses-only on OpenAI, and LiteLLM's bundled map has no entry for them, so LiteLLM would not route them on its own. A Kiln routing flag is what would make direct entries possible. |

### 2c. Thinking levels hidden because of Chat Completions

Read:

- `GPT_6_1_SOL_OPENAI_THINKING_LEVELS` ([L584-594](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L584)): "The model page lists `max` as well, but /v1/chat/completions (which Kiln uses) rejects it with a 400; only /v1/responses accepts it."
- GPT-6.1 Terra direct uses `GPT_5_4_OPENAI_THINKING_LEVELS` ([L1033-1035](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1033)): "/v1/chat/completions accepts none through xhigh for this model and rejects max with a 400."
- GPT-6 Astra, Sol and Luna direct **do** list `max` (`GPT_6_ASTRA_OPENAI_THINKING_LEVELS` [L576-582](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L576), `GPT_6_OPENAI_THINKING_LEVELS` [L597-604](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L597)). Whether Chat Completions accepts `max` for them is not stated in the code (history subtopic).

### 2d. Azure OpenAI

Only GPT-4.1 family, GPT-4o family and o1/o3/o3-mini/o4-mini tiers. No GPT-5.x. Not affected today.

## 3. Remote model list: how older app versions load providers

Read, unless marked.

- **Source and URL.** Clients fetch `https://remote-config.getkiln.ai/kiln_config_v2.json` ([remote_config.py:34](../../../../libs/core/kiln_ai/adapters/remote_config.py#L34)) in a background thread at desktop startup ([desktop_server.py:141-142](../../../../app/desktop/desktop_server.py#L141)), unless `KILN_SKIP_REMOTE_MODEL_LIST=true`. The web model library page fetches the same URL directly in the browser ([models/+page.svelte:194](../../../../app/web_ui/src/routes/%28app%29/models/+page.svelte#L194)). "Only v2 is published: v0.18's remote-config handling was buggy, so its v1 URL stays absent and those clients fall back to the built-in list." So **every client from v0.19 on reads one file**; there is no per-version file or version field.
- **Publishing.** The JSON is generated by `python -m kiln_ai.adapters.remote_config` from the `remote_config` branch on push ([.github/workflows/publish_remote_config.yml](../../../../.github/workflows/publish_remote_config.yml)), after a compatibility test that installs `kiln-ai==0.19.0` and parses the new JSON ([test_remote_config.py:1400-1466](../../../../libs/core/kiln_ai/adapters/test_remote_config.py#L1400)). The model-sweep skill describes the process: `remote_config` only ever takes `main`, through a PR a human merges ([kiln-model-sweep/SKILL.md:105-111](../../../../.agents/skills/kiln-model-sweep/SKILL.md#L105)). So the team controls when a model-list change reaches old clients, but once published it reaches all of them at once.
- **Serialization.** `serialize_config` writes `model_dump(mode="json")` for each model ([remote_config.py:51-62](../../../../libs/core/kiln_ai/adapters/remote_config.py#L51)), so every field, including defaults, appears for every provider.
- **Deserialization** ([remote_config.py:72-201](../../../../libs/core/kiln_ai/adapters/remote_config.py#L72)): each provider is validated on its own with `KilnModelProvider.model_validate`; unknown MIME types are filtered first; a provider that fails validation is **dropped with a warning** ("Upgrade Kiln to use this model"); the model is kept with the providers that passed. A model that fails validation is dropped.
- **Unknown fields are ignored.** Tested by `test_deserialize_config_with_extra_keys` and `test_deserialize_config_provider_with_extra_fields` ([test_remote_config.py:347-381](../../../../libs/core/kiln_ai/adapters/test_remote_config.py#L347), [L912+](../../../../libs/core/kiln_ai/adapters/test_remote_config.py#L912)).
- **Unknown enum values drop the provider.** A `name` not in the client's `ModelProviderName` fails validation (tested with `"unknown-provider-123"`, [test_remote_config.py:518-640](../../../../libs/core/kiln_ai/adapters/test_remote_config.py#L518)). The Jev work relied on this: "Older clients never see the Jev entry anyway because they drop unknown provider names" ([specs/projects/jev_provider/architecture.md:60](../../../../specs/projects/jev_provider/architecture.md#L60)).
- **The swap.** `refresh_model_list` replaces `built_in_models[:]` in place under a lock ([L221-231](../../../../libs/core/kiln_ai/adapters/remote_config.py#L221)).

### What this means for a migration (Inference, from the facts above)

1. A new routing field (say a boolean or an enum on `KilnModelProvider`) is **ignored** by every client that predates it. Its presence alone never drops the provider.
2. If the same publish also flips `supports_function_calling=True` on the ten entries (or adds `max` to GPT-6.1 Sol/Terra), every older client gets those values without the routing code. Those clients would show these models for tool runs and then send tools + `reasoning_effort` (or `max`) to `/v1/chat/completions`. What that does on each old client depends on the LiteLLM version it pinned (history subtopic). This is the same class of problem as the "release-gating rule" for new providers in [claude-maintain-models/SKILL.md:495-520](../../../../.agents/skills/claude-maintain-models/SKILL.md#L495), but that rule's fix (wait for a release) does not help users who never upgrade.
3. Levers that exist in the code today, none of them designed for this:
   - Keep `supports_function_calling=False` in the published data and have new clients compute effective tool support from the new field. Old clients keep today's behavior.
   - Put a value an old client cannot validate into an existing field, so old clients drop just that provider. `adapter: ModelAdapterId` is ignored entirely by clients before v1.2.0 (unknown key), so a new `ModelAdapterId` value would only drop the provider on v1.2.0+. A new `ModelProviderName` would drop it everywhere but changes the provider id saved in run configs.
   - Delay the remote-config publish (the existing release-gating practice).
4. `user_model_to_provider` copies any `KilnModelProvider` field from a user model's `overrides` except `name`, `model_id` and `adapter` ([provider_tools.py:423-473](../../../../libs/core/kiln_ai/adapters/provider_tools.py#L423)), so a new field is automatically overridable for user-added models. A user who adds a not-yet-listed OpenAI model as a built-in-provider user model gets the field's default. If the goal is "every OpenAI model released after GPT-5.4", the default (or a rule on provider name) decides whether such user models are routed.

## 4. Where `supports_function_calling` is read

Read (grep of `libs/` and `app/`, non-test):

- Not read by any adapter, so the runtime never enforces it.
- Exposed as `ModelDetails.supports_function_calling` by the available-models API ([provider_api.py:160-186](../../../../app/desktop/studio_server/provider_api.py#L160), set at [L330](../../../../app/desktop/studio_server/provider_api.py#L330)).
- Web UI: the run-config model dropdown moves models to "unsupported" when the run config needs tools ([available_models_dropdown.svelte:235-236](../../../../app/web_ui/src/lib/ui/run_config_component/available_models_dropdown.svelte#L235)); the models page shows a capability badge ([models/+page.svelte:256](../../../../app/web_ui/src/routes/%28app%29/models/+page.svelte#L256), [L409-413](../../../../app/web_ui/src/routes/%28app%29/models/+page.svelte#L409), [L1041](../../../../app/web_ui/src/routes/%28app%29/models/+page.svelte#L1041)); the fine-tune page uses it for tool training data; the add-model page lets users override it.
- Fine-tune API: `supports_tools = provider.supports_function_calling and provider.name != together_ai` ([finetune_api.py:429-432](../../../../app/desktop/studio_server/finetune_api.py#L429)).
- Paid tests: `test_tools_all_built_in_models` skips providers with `supports_function_calling=False` ([test_litellm_adapter_tools.py:231-251](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py#L231)). Flipping the flag adds those ten providers to that paid fan-out automatically.

## 5. Docs and skills a migration would make stale

Read (grep of `.agents/`): the OpenAI section of [claude-maintain-models/SKILL.md:605-609](../../../../.agents/skills/claude-maintain-models/SKILL.md#L605) and its thinking-levels table ([L754-759](../../../../.agents/skills/claude-maintain-models/SKILL.md#L754)) say nothing about function calling or endpoints for GPT-5.4+; any new flag needs a line there. `kiln-conventions/references/core.md` describes the model list and remote list swap. The model-sweep skill adds models daily, so whatever rule decides routing for new OpenAI models must be written where that skill will read it.
