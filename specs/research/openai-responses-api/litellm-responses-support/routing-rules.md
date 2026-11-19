# Routing rules: when a LiteLLM chat call goes to `/v1/responses`

Scope: LiteLLM 1.102.0 as installed in Kiln's virtualenv (`.venv/lib/python3.13/site-packages/litellm/`), compared with later releases downloaded from PyPI (1.102.4, 1.103.10, 1.104.8, 1.105.0, 1.105.7, 1.106.0, 1.106.6, 1.108.0rc1). Paths below are relative to the `litellm` package directory unless noted. "Bridge" means LiteLLM's chat-to-responses conversion layer in `completion_extras/litellm_responses_transformation/`.

## Where the decision is made

`litellm.completion()` / `acompletion()` call `responses_api_bridge_check()` (`main.py:1047`) twice:

1. Early, right after `get_llm_provider()` (`main.py:5349`), with only `model`, `custom_llm_provider`, `web_search_options` and `api_base`. This catches the prefix and model-map rules and strips `responses/` from the model name before parameter validation runs.
2. Late, after `get_optional_params()` has run the chat-side parameter mapping (`main.py:5600-5611`), and only if the first call did not already pick Responses. This call also gets `tools`, `reasoning_effort`, and a reasoning summary read from `optional_params` by `peek_reasoning_summary_aliases()`.

If either call returns `mode == "responses"`, `completion()` hands the already chat-mapped `optional_params` to `responses_api_bridge.completion()` (`main.py:5616-5651`). It does this unless the internal kwarg `_skip_responses_api_bridge` is set (used by the reverse bridge to avoid infinite recursion).

Consequence worth knowing: chat-side parameter validation for the OpenAI GPT-5 config (`llms/openai/chat/gpt_5_transformation.py`) has already run before the bridge sees the request. So chat-side drops and errors (temperature, logprobs, `max_tokens` renaming) apply to bridged calls too. See [request-mapping.md](./request-mapping.md).

## The rules, in evaluation order

Quoted from `main.py:1047-1143` (1.102.0).

| # | Rule | Applies to | Source |
|---|---|---|---|
| 1 | `litellm.route_all_chat_openai_to_responses` is true (env `LITELLM_ROUTE_ALL_CHAT_OPENAI_TO_RESPONSES=true`) | provider `openai` only; returns early | `main.py:1060-1063`, `__init__.py:263-265` |
| 2 | Model map entry for the model has `mode: "responses"` | any provider whose map entry says so | `main.py:1066-1069` via `_get_model_info_helper` |
| 3 | Model name starts with `responses/` (from `openai/responses/<m>` or `azure/responses/<deployment>`) and the map has no mode for it | any provider; the prefix is stripped | `main.py:1070-1073` (and 1080-1084 when map lookup throws, "handle azure models") |
| 4 | `web_search_options` given and provider is `xai` | xAI only | `main.py:1075-1077` |
| 5 | GPT-5 family name, not a search model, provider `openai` or `azure`, and either (a) `reasoning_effort` is set and a reasoning summary alias is present, or (b) gpt-5.4-or-newer name + at least one `type: "function"` tool + reasoning active + (effort explicitly set, or the endpoint is known to enforce the constraint) | `openai`, `azure` | `main.py:1086-1141` |

Rule 5 details, quoted:

```python
has_function_tool: Final = any(
    (tool.get("type") == "function" if isinstance(tool, dict) else getattr(tool, "type", None) == "function")
    for tool in (tools or ())
)
if isinstance(reasoning_effort, dict):
    reasoning_active = reasoning_effort.get("effort") != "none" or reasoning_effort.get("summary") is not None
else:
    reasoning_active = reasoning_effort != "none"
...
on_constraint_enforcing_endpoint: Final = (
    custom_llm_provider == "azure" or resolved_api_base == "" or _is_openai_backed_api_base(resolved_api_base)
)
if (
    custom_llm_provider in ("openai", "azure")
    and model_info.get("mode") != "responses"
    and OpenAIGPT5Config.is_model_gpt_5_model(model)
    and not OpenAIGPT5Config.is_model_gpt_5_search_model(model)
    and (
        (reasoning_effort is not None and reasoning_summary is not None)
        or (
            OpenAIGPT5Config.is_model_gpt_5_4_plus_model(model)
            and has_function_tool
            and reasoning_active
            and (reasoning_effort is not None or on_constraint_enforcing_endpoint)
        )
    )
):
    model_info["mode"] = "responses"
```

The comment above this block in the source explains the rule: "OpenAI enables reasoning by default for these models (unset reasoning_effort means medium server-side), and Chat Completions rejects function tools whenever reasoning is on ("Function tools with reasoning_effort are not supported ... use /v1/responses or set reasoning_effort to 'none'"), so only an explicit ``"none"`` keeps the request chat-servable. Custom (grammar) tools are served natively by Chat Completions with reasoning on, so custom-only requests stay on chat."

### How model names are classified

From `llms/openai/chat/gpt_5_transformation.py` (1.102.0):

- `is_model_gpt_5_model(model)` is `is_gpt_reasoning_series_name()`: true when the name contains `"gpt-5"` or `"gpt-6"` and the last path segment does not start with `gpt-5-chat` (lines 64-68, 83-84).
- `is_model_gpt_5_4_plus_model(model)`: true when the last path segment starts with `gpt-6`, or starts with `gpt-5.` and the minor number is at least 4 (lines 116-128).
- Names after `gpt-6` (for example a hypothetical `gpt-7`) match neither rule. The automatic rule will not route them. This is still true in 1.108.0rc1 (`GPT_REASONING_SERIES_MARKERS = ("gpt-5", "gpt-6")` in `llms/openai/chat/gpt_5_transformation.py:71` of that wheel).

### Which hosts count as "constraint-enforcing"

`_resolve_openai_api_base()` resolves the base the same way the chat handler does: `api_base` argument, then `litellm.api_base`, then `OPENAI_BASE_URL`, then `OPENAI_API_BASE`, then `https://api.openai.com/v1` (`main.py:1032-1044`). `_is_openai_backed_api_base()` accepts `api.openai.com` and any subdomain (for example PrivateLink and regional hosts). Azure always counts. Any other host, such as a local proxy or OpenAI-compatible gateway, only bridges when `reasoning_effort` is set explicitly. This host check came from PR [#39587](https://github.com/BerriAI/litellm/pull/39587) (merged 2026-09-03, included in 1.102.0 which was published 2026-09-20). That PR quotes the OpenAI error it works around: "Function tools with reasoning_effort are not supported for gpt-5.6 in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'".

## Observed routing (experiment)

Script: `/tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/litellm_wire/routing_check.py`. It calls `responses_api_bridge_check()` directly and then makes real `litellm.acompletion()` calls against a local fake HTTP server. `LITELLM_LOCAL_MODEL_COST_MAP=True` was set so the bundled model map is used. Output (abridged; `mode=None` and `mode=chat` both mean "stays on chat"):

```text
openai     gpt-5.4                  tools=function effort=None    base=default                  -> mode=responses
openai     gpt-5.4                  tools=function effort=none    base=default                  -> mode=chat
openai     gpt-5.4                  tools=function effort=high    base=default                  -> mode=responses
openai     gpt-5.4                  tools=function effort={'effort': 'none', 'summary': 'auto'} -> mode=responses
openai     gpt-5.4                  tools=none     effort=high    base=default                  -> mode=chat
openai     gpt-5.4                  tools=custom   effort=high    base=default                  -> mode=chat
openai     gpt-5.5                  tools=function effort=None    base=default                  -> mode=responses
openai     gpt-5.6-sol              tools=function effort=max     base=default                  -> mode=responses
openai     gpt-6.1-sol              tools=function effort=None    base=default                  -> mode=responses
openai     gpt-7                    tools=function effort=high    base=default                  -> mode=None
openai     gpt-5.2                  tools=function effort=high    base=default                  -> mode=chat
openai     gpt-5.2                  tools=none     effort=high    summary=auto                  -> mode=responses
openai     gpt-5.2                  tools=none     effort=None    summary=auto                  -> mode=chat
openai     gpt-5.4-pro              tools=none     effort=None                                  -> mode=responses
openai     gpt-5-codex / o3-pro     tools=none     effort=None                                  -> mode=responses
openai     responses/gpt-4.1        tools=none                                                  -> mode=responses model=gpt-4.1
openai     gpt-5.4                  tools=function effort=None    base=http://127.0.0.1:9999/v1 -> mode=chat
openai     gpt-5.4                  tools=function effort=high    base=http://127.0.0.1:9999/v1 -> mode=responses
openai     gpt-5.4                  tools=function effort=None    base=https://eu.api.openai.com/v1 -> mode=responses
openrouter gpt-5.4                  tools=function effort=high                                  -> mode=None
azure      gpt-5.4                  tools=function effort=None    base=https://x.openai.azure.com -> mode=responses
azure      my-deployment            tools=function effort=high    base=https://x.openai.azure.com -> mode=None
azure      responses/my-deployment  tools=none     effort=None                                  -> mode=responses model=my-deployment
route_all_chat_openai_to_responses=True, openai gpt-4.1 -> mode=responses
```

End to end against the fake server (paths actually hit):

```text
openai/gpt-5.4            tools=yes {}                                   -> ['/v1/chat/completions']   (custom base, effort unset)
openai/gpt-5.4            tools=yes {'reasoning_effort': 'high'}         -> ['/v1/responses']
openai/gpt-5.4            tools=yes {'reasoning_effort': 'none'}         -> ['/v1/chat/completions']
openai/gpt-5.4            tools=no  {'reasoning_effort': 'high'}         -> ['/v1/chat/completions']
openai/gpt-5.2            tools=no  {'reasoning_effort': 'high', 'reasoning_summary': 'auto'} -> ['/v1/responses']
openai/gpt-5.2            tools=no  {'reasoning_effort': 'high', 'extra_body': {'reasoningSummary': 'auto'}} -> ['/v1/responses']
openai/responses/gpt-4.1  tools=no  {}                                   -> ['/v1/responses']
openai/gpt-5.4-pro        tools=no  {}                                   -> ['/v1/responses']
```

Reading of these results:

- With LiteLLM 1.102.0, a gpt-5.4+ OpenAI-direct call that has function tools goes to `/v1/responses` on its own unless `reasoning_effort` is the string `"none"` (rule 5b). Setting `supports_function_calling=False` is not needed to stop a Chat Completions 400 with this LiteLLM version. But turning tools back on with 1.102.x sends those calls through the bridge, with the defects in [known-defects.md](./known-defects.md), including the two-choice split that hides tool calls from a `choices[0]` reader. Whether Kiln's workaround is still needed is the history subtopic's question; this is the LiteLLM side of it.
- The same request without tools stays on `/v1/chat/completions`, even with reasoning on. So a Kiln task on gpt-5.4 can hit two different endpoints depending on whether tools are attached. The reply shape, ids and error types differ between the two (see [reply-and-streaming-mapping.md](./reply-and-streaming-mapping.md)).
- The routing depends on the base URL. A test that points `api_base` at a local mock server and leaves `reasoning_effort` unset sees Chat Completions, while production on `api.openai.com` sees Responses.
- Any future OpenAI model name outside the `gpt-5*` / `gpt-6*` patterns (or not in the model map as `mode: responses`) is not routed automatically.

## Reasoning summary aliases

`peek_reasoning_summary_aliases()` (`utils.py:9839-9854`) looks for, in order: `reasoningSummary` and `reasoning_summary` at the top level of `optional_params`, then the same two keys inside `extra_body`. When the call bridges, `strip_reasoning_summary_aliases_from_optional_params()` (`utils.py:9857-9880`) removes them and `main.py:5621-5633` folds the value into `reasoning_effort` as a dict: `{"effort": <effort>, "summary": <value>}`. When the call does not bridge and the model is GPT-5 family on OpenAI or Azure, the aliases are stripped and silently dropped (`main.py:5652-5656`). Rule 5a only fires with both `reasoning_effort` and a summary alias; a summary alias alone keeps the call on chat (see the `gpt-5.2 effort=None summary=auto -> chat` row).

## `mode: responses` in the model map, and where the map comes from

Entries in the bundled map with `mode: "responses"` for provider `openai` include `codex-mini-latest`, `gpt-5-codex`, `gpt-5.1-codex*`, `gpt-5.2-codex`, `gpt-5.3-codex`, `gpt-5-pro`, `gpt-5.2-pro`, `gpt-5.4-pro`, `gpt-5.5-pro`, `o1-pro`, `o3-pro`, `o3-deep-research`, `o4-mini-deep-research` and `gpt-daybreak-*-latest`. All base gpt-5.x and gpt-6 models are `mode: "chat"` with `/v1/responses` listed in `supported_endpoints` (read from `model_prices_and_context_window_backup.json` in the installed wheel).

The map is not fixed per LiteLLM version. At import, `litellm/__init__.py:422-426,557` fetches `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` unless `LITELLM_LOCAL_MODEL_COST_MAP=true` is set. It falls back to the bundled copy on failure (`litellm_core_utils/get_model_cost_map.py:601-660`). So rule 2 (and the reasoning-effort capability checks in the chat config) can change for a deployed app when BerriAI edits the map on `main`, with no LiteLLM upgrade. The LiteLLM docs say the same: "The model's default `mode` determines how bridging works. (see `model_prices_and_context_window`)" ([/responses docs](https://docs.litellm.ai/docs/response_api)).

## Documentation versus code

The LiteLLM OpenAI provider page ([docs.litellm.ai/docs/providers/openai](https://docs.litellm.ai/docs/providers/openai), fetched 2026-10-30, reflects `main`) documents:

- "[BETA] Route all .completions requests to Responses API (better quality)" with the `openai/responses/` prefix and `route_all_chat_openai_to_responses`. It states: "`route_all_chat_openai_to_responses` only applies to the `openai` provider. Azure OpenAI is unaffected." The flag was added by PR [#25359](https://github.com/BerriAI/litellm/pull/25359).
- A tip box that says "LiteLLM drops `reasoning_effort` from `gpt-5.4` and newer ... requests to `litellm.completion()` that include tools" and then "LiteLLM also auto-routes these requests to `/v1/responses` when both `tools` and `reasoning_effort` are set". The first sentence does not match 1.102.0, which bridges rather than drops, and also bridges when `reasoning_effort` is unset on `api.openai.com`. The route-instead-of-drop change came from PRs [#23576](https://github.com/BerriAI/litellm/pull/23576)/[#23577](https://github.com/BerriAI/litellm/pull/23577) (March 2026). The unset-effort arm came from PR [#33237](https://github.com/BerriAI/litellm/pull/33237) and the host check from [#39587](https://github.com/BerriAI/litellm/pull/39587).

## Changes after 1.102.0

- 1.102.1 to 1.102.4: `responses_api_bridge_check` and both bridge files are byte-identical to 1.102.0 (diffed).
- 1.106.6: `reasoning_active` also counts as true when the model's map row refuses `reasoning_effort="none"` (`_chat_gate_refuses_reasoning_effort_none`). A function tool must now have a `function` dict or a `name` to count. A separate `azure_ai` (Azure AI Foundry) arm was added with different model cut-offs. The 1.106.6 source comment says Foundry rejects "an explicit effort with function tools ... from gpt-5.6 on, and the unset effort only from gpt-6 on".
- 1.108.0rc1 (2026-10-29): the function moved to `litellm/responses/bridge_check.py`. It still keys on the `gpt-5`/`gpt-6` name markers.
