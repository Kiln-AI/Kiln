---
status: complete
---

# Phase 2: Connect, disconnect and web UI for OpenCode

## Overview

Let users connect and disconnect OpenCode from the desktop app. The studio server validates a pay-as-you-go Console key with a free `GET /inference/v1/models` call before saving it, and disconnect clears the key. The web UI gets the friendly name, the icon and a connect card with the approved copy. Regenerating the API schema and handling `opencode` in the exhaustive matches close the `ty` and schema-check failures that phase 1 left open.

## Steps

1. `app/desktop/studio_server/provider_api.py`:
   - Module constants next to the other provider constants:
     ```python
     OPENCODE_MODELS_URL = "https://opencode.ai/inference/v1/models"
     OPENCODE_CONNECT_TIMEOUT_SECONDS = 10
     ```
   - `async def connect_opencode(key: str) -> JSONResponse`, using `httpx.AsyncClient` with `Authorization: Bearer {key}`, the 10 s timeout and `follow_redirects=True`:
     - 200: `Config.shared().opencode_api_key = key`, return 200 `"Connected to OpenCode"`.
     - 401 or 403: return 401 `"Invalid OpenCode API key. Use a pay-as-you-go API key from OpenCode Console; OpenCode Go subscriptions aren't supported."`
     - any other status: return 400 `"Failed to connect to OpenCode. Error: [{status}]"`.
     - `httpx.RequestError` (covers timeouts): return 400 `"Couldn't reach OpenCode. Check your network connection and try again."`
     - The key is saved only on 200.
   - `connect_api_key`: `case ModelProviderName.opencode: return await connect_opencode(parse_api_key(key_data))`.
   - `disconnect_api_key`: `case ModelProviderName.opencode: Config.shared().opencode_api_key = None`.

2. Regenerate `app/web_ui/src/lib/api_schema.d.ts` with `app/web_ui/src/lib/generate_schema.sh` (adds `"opencode"` to `ModelProviderName`).

3. `app/web_ui/src/lib/stores.ts`: `opencode: "OpenCode"` in `provider_name_map`.

4. `app/web_ui/src/lib/ui/provider_image.ts`: `opencode: "/images/opencode.svg"`; copy `specs/projects/opencode_provider/assets/opencode.svg` unchanged to `app/web_ui/static/images/opencode.svg`.

5. `app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte`:
   - A provider card after TypeSafe AI:
     ```ts
     {
       name: "OpenCode",
       id: "opencode",
       description: "Pay-as-you-go access to models from Anthropic, OpenAI, Google and more, billed to your OpenCode credits.",
       featured: false,
       api_key_warning: "Uses OpenCode's pay-as-you-go credits. OpenCode Go subscriptions aren't supported.",
       api_key_steps: [
         "Sign in to OpenCode Console at https://opencode.ai/console and add pay-as-you-go credits to your workspace.",
         "Open Account, then Personal API keys, and click Add API key.",
         "Copy the key and paste it below.",
       ],
       api_key_fields: ["API Key"],
     }
     ```
   - An `opencode` entry in `status`, and `if (data["opencode_api_key"]) status.opencode.connected = true` in the saved-settings check.

## Tests

`app/desktop/studio_server/test_provider_api.py`:
- `test_connect_opencode_success`: 200 saves the key, returns 200 "Connected to OpenCode", and the GET goes to the models URL with the bearer header, the 10 s timeout and `follow_redirects=True`.
- `test_connect_opencode_invalid_api_key` (401, 403): returns 401 with the pay-as-you-go message; the key isn't saved.
- `test_connect_opencode_other_error` (400, 429, 500, 503): returns 400 with the status in the message; the key isn't saved.
- `test_connect_opencode_network_error` (`httpx.ConnectError`, `httpx.ReadTimeout`): returns 400 "Couldn't reach OpenCode…", never the invalid-key message; the key isn't saved.
- `test_connect_api_key_opencode_success`: `connect_api_key` dispatches to `connect_opencode` with the parsed key.
- `test_disconnect_api_key_opencode`: clears `opencode_api_key` and leaves other providers' keys.
- Add `opencode` to `test_connect_api_key_invalid_payload` and `opencode_api_key` to the `mock_config_all_providers` fixture.

`connect_providers.test.ts`:
- OpenCode shows as connected when `opencode_api_key` is saved.
- The OpenCode dialog shows the Go warning and the three key steps, with the Console URL linked.
