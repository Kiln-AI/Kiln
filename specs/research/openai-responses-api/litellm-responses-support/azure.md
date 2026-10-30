# Azure OpenAI through the same layers

Scope: LiteLLM 1.102.0. Code: `llms/azure/responses/transformation.py`, `llms/azure/responses/o_series_transformation.py`, `llms/azure/common_utils.py`, `main.py` (`responses_api_bridge_check`). Experiments: `/tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/litellm_wire/native_and_azure.py` / `.out` and `azure_stream_check.py` / `.out`, against a local fake server standing in for `https://<resource>.openai.azure.com`.

## Routing

The bridge rules for Azure are in [routing-rules.md](./routing-rules.md). Azure-specific points:

- Azure always counts as a "constraint-enforcing endpoint", so a gpt-5.4+ name with a function tool and no explicit `reasoning_effort="none"` bridges even when the effort is unset.
- The name test runs on the **deployment name** in `azure/<deployment>`. `responses_api_bridge_check` is called with `model=model`, not `base_model` (`main.py:5602-5610`). A deployment named after the model (`azure/gpt-5.4`) is detected. A deployment with any other name (`azure/my-gpt54-deployment`) is not.
- `route_all_chat_openai_to_responses` does not apply to Azure (`main.py:1060`; LiteLLM docs: "Azure OpenAI is unaffected").
- The explicit opt-in for Azure is the `azure/responses/<deployment>` prefix (`main.py:1080-1084`, comment "handle azure models - `azure/responses/<deployment-name>`").

Observed:

```text
azure/gpt-5.4                        {}                                                     -> /openai/responses?api-version=2025-04-01-preview  (bridged, choices=2)
azure/my-gpt54-deployment            {'reasoning_effort': 'high'}                           -> EXC UnsupportedParamsError: azure does not support parameters: ['reasoning_effort'], for model=my-gpt54-deployment
azure/my-gpt54-deployment            {'reasoning_effort': 'high', 'base_model': 'azure/gpt-5.4'} -> /openai/deployments/my-gpt54-deployment/chat/completions?api-version=2025-04-01-preview  (not bridged)
azure/responses/my-gpt54-deployment  {'reasoning_effort': 'high'}                           -> /openai/responses?api-version=2025-04-01-preview  (bridged, body.model=my-gpt54-deployment)
```

The third row is the Kiln-relevant trap: with `base_model` set so LiteLLM knows the deployment is gpt-5.4, the chat-side validation accepts `reasoning_effort`, but the request still goes to Chat Completions with tools and reasoning. Per the OpenAI error that LiteLLM's code comments cite, Azure is expected to reject that combination for gpt-5.4+. I could not confirm that against real Azure.

## URL, auth and body

- URL: `BaseAzureLLM._get_base_azure_url(route="/openai/responses", default_api_version=AZURE_DEFAULT_RESPONSES_API_VERSION)` (`llms/azure/responses/transformation.py:159-186`, `llms/azure/common_utils.py:743-800`). The default version is env `AZURE_DEFAULT_RESPONSES_API_VERSION` or `"preview"` (`constants.py:9`). The versions `preview`, `latest` and `v1` switch the path to `/openai/v1/responses` (`_is_azure_v1_api_version`, `common_utils.py:821-824`). Observed: no `api_version` gave `/openai/v1/responses?api-version=preview`; `api_version="2025-04-01-preview"` gave `/openai/responses?api-version=2025-04-01-preview`.
- Auth: Azure environment validation (`api-key` header was present in the capture), `llms/azure/responses/transformation.py:47-48`.
- Body `model` is the deployment name with any `responses/` or `o_series/` prefix stripped (`get_stripped_model_name`, lines 50-56).
- Tools nested under `function` are flattened (lines 128-142). The bridge already flattens them, so the bridged body was the same shape as for OpenAI, including `"strict": null` and `"description": null`.
- Input items: `status` is removed from reasoning items and from message items, because "Azure OpenAI API does not accept 'status' field in input messages" (lines 58-118, citing issue [#13484](https://github.com/BerriAI/litellm/issues/13484)).
- `context_management` is not supported on Azure (line 27).
- `AzureOpenAIOSeriesResponsesAPIConfig` is chosen when the model is an o-series name or `supports_reasoning(model)` is true (`utils.py:8791-8801`). It removes `temperature` from supported params and drops it under `drop_params` (`o_series_transformation.py`).
- Temperature rules for GPT-5 names use `AzureOpenAIGPT5Config` (lines 34-40).

## Streaming

An Azure deployment name that is not a model-map key is fake-streamed on the Responses path. LiteLLM sends one non-streaming request and synthesizes the chunks afterwards. Observed:

```text
azure/responses/my-gpt54-deployment  path=/openai/v1/responses?api-version=preview  stream sent upstream=None  chunks=14
azure/responses/gpt-5.4              path=/openai/v1/responses?api-version=preview  stream sent upstream=True  chunks=10
```

Cause: `OpenAIResponsesAPIConfig.should_fake_stream()` (inherited by Azure) returns true when `supports_native_streaming()` fails to find the model (`llms/openai/responses/transformation.py:710-730`, `utils.py:2514-2545`). Onyx patches this ([onyx#13192](https://github.com/onyx-dot-app/onyx/pull/13192)).

## Later releases

- 1.106.x adds an `azure_ai` (Azure AI Foundry OpenAI v1 host) arm to the bridge check with different cut-offs. The source comment says Foundry rejects "an explicit effort with function tools ... from gpt-5.6 on, and the unset effort only from gpt-6 on (gpt-5.6 serves tools with reasoning silently off)".
- v1.106.2 release notes: "Azure `gpt-6-astra` refuses `none` and `gpt-5.3-codex` refuses `minimal`", checked against the model map and returned as a 400 from LiteLLM, or dropped under `drop_params` (PR #43935, [v1.106.2 notes](https://docs.litellm.ai/release_notes/v1.106.2/v1-106-2)).
- I found no change that makes the bridge check use `base_model` for Azure deployment names.
