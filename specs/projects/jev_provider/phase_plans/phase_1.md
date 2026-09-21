---
status: complete
---

# Phase 1: Provider plumbing for TypeSafe AI

## Overview

Register TypeSafe AI as a Kiln provider so the rest of the project has an enum member, a
stored API key, a friendly name, a missing-key warning, and a Settings connect/disconnect
flow to build on. No model entry, no adapter, no routing, no UI — those are later phases.

The two LiteLLM switch sites get an explicit `typesafe` case that raises, because TypeSafe
never runs through LiteLLM; leaving them on the exhaustive `case _` would be a silent
mis-route once the model entry lands.

The connect flow validates the key against `GET https://api.typesafe.ai/v1/models`. The
architecture asks to first confirm that endpoint rejects a bad key; egress to
`api.typesafe.ai` is blocked by this sandbox's proxy, so the evidence is indirect: the
official `typesafe-sdk` 0.7.0 refuses to construct a client without an API key, sends
`Authorization` on every request including `models.list()`, and documents that call as
listing "the models available to the account". Account-scoped and always authenticated,
so a bad key must 401. Noted in the return summary so a human can confirm against a live
key; the test suite mocks both branches, so switching to the minimal-POST fallback later
touches only `connect_typesafe`.

## Steps

1. `libs/core/kiln_ai/datamodel/datamodel_enums.py` — add `typesafe = "typesafe"` to the
   end of `ModelProviderName`.

2. `libs/core/kiln_ai/utils/config.py` — add to `Config` properties, next to the other
   provider keys:
   ```python
   "typesafe_api_key": ConfigProperty(
       str,
       env_var="TYPESAFE_API_KEY",
       sensitive=True,
   ),
   ```

3. `libs/core/kiln_ai/utils/litellm.py` — in `get_litellm_provider_info`, add before the
   `case _`:
   ```python
   case ModelProviderName.typesafe:
       raise ValueError("TypeSafe AI models do not run through LiteLLM")
   ```

4. `libs/core/kiln_ai/adapters/provider_tools.py`, three sites:
   - `provider_name_from_id`: `case ModelProviderName.typesafe: return "TypeSafe AI"`
   - `provider_warnings`: `ModelProviderName.typesafe: ModelProviderWarning(
     required_config_keys=["typesafe_api_key"], message="Attempted to use TypeSafe AI
     without an API key set. \nGet your API key from https://typesafe.ai")`
   - `lite_llm_core_config_for_provider`: `case ModelProviderName.typesafe:` raises
     `ValueError("TypeSafe AI models do not run through LiteLLM")`

5. `app/desktop/studio_server/provider_api.py` — add `connect_typesafe(key: str)` beside
   `connect_cerebras`, modelled on it:
   ```python
   async def connect_typesafe(key: str):
       # GET /v1/models is account-scoped, so it rejects a bad key without spending tokens.
       response = requests.get("https://api.typesafe.ai/v1/models", headers=...)
   ```
   200 → store `Config.shared().typesafe_api_key`, 200 `"Connected to TypeSafe AI"`.
   401/403 → 401 `"Failed to connect to TypeSafe AI. Invalid API key."`.
   Other non-2xx → 400 `"Failed to connect to TypeSafe AI. Error: [<status>]"`.
   Exception → 400 `"Failed to connect to TypeSafe AI. Error: <message>"`.
   Wire `case ModelProviderName.typesafe: return await connect_typesafe(parse_api_key(key_data))`
   into `connect_api_key`, and `Config.shared().typesafe_api_key = None` into
   `disconnect_api_key`.

## Tests

- `test_provider_tools.py::test_provider_name_from_id_parametrized` — add the
  `(typesafe, "TypeSafe AI")` case.
- `test_provider_tools.py::test_provider_warnings_typesafe_missing_key` —
  `check_provider_warnings(typesafe)` raises when `typesafe_api_key` is unset, and is
  silent when set.
- `test_provider_tools.py::test_lite_llm_core_config_for_provider_typesafe_raises` —
  `lite_llm_core_config_for_provider(typesafe)` raises `ValueError` naming LiteLLM.
- `test_litellm_adapter.py::test_litellm_model_id_typesafe_not_supported` —
  `get_litellm_provider_info` on a typesafe provider raises `ValueError`.
- `test_config.py` — `typesafe_api_key` reads from the `TYPESAFE_API_KEY` env var and is
  reported sensitive.
- `test_provider_api.py::test_connect_typesafe_success` — 200 stores the key and returns
  the connected message, with the expected URL and Bearer header.
- `test_provider_api.py::test_connect_typesafe_invalid_api_key` — 401 and 403 both return
  401 and do not store the key.
- `test_provider_api.py::test_connect_typesafe_other_error` — 400/429/500 return 400 with
  the status and do not store the key.
- `test_provider_api.py::test_connect_typesafe_request_exception` — a raised exception
  returns 400 with the message and does not store the key.
- `test_provider_api.py::test_connect_api_key_typesafe_success` — the dispatch calls
  `connect_typesafe` with the parsed key.
- `test_provider_api.py::test_disconnect_api_key_typesafe` — clears `typesafe_api_key`
  and leaves other provider keys alone.
- `test_provider_api.py::test_connect_api_key_invalid_payload` — add `typesafe` to the
  parametrized provider list.
