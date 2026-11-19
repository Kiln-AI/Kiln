---
status: complete
---

# Phase 3: Summaries setting in the app

## Overview

Phase 2 added the global setting `open_ai_reasoning_summaries` (default off) and everything that uses it in the adapter. Nothing sets it yet. This phase lets the user turn it on when they connect OpenAI, and turns it off when they disconnect.

The OpenAI API-key dialog on the connect-providers screen gets one checkbox, "Show reasoning summaries (requires Org verification)", with an (i) tooltip that explains organization verification. The dialog sends the checkbox value to the desktop connect endpoint in a new optional `options` object. The endpoint saves the setting with the key, only after the key check succeeds. Disconnecting OpenAI turns the setting off. The same dialog serves onboarding and Settings → Providers.

The maintainer skill gets a note on the `openai_reasoning_summary` provider field, and the `docs-sync` skill runs over the branch.

## Steps

1. **Connect endpoint** (`app/desktop/studio_server/provider_api.py`).
   - Next to `parse_api_key` inside `connect_provider_api`, add:

     ```python
     def parse_connect_options(payload: dict) -> dict[str, bool]:
     ```

     It returns `payload.get("options", {})` when that is a dict whose keys are all `str` and whose values are all `bool`. Otherwise it raises `HTTPException(status_code=400, detail="Invalid options")`, which `connect_custom_errors` returns as `{"message": "Invalid options"}`, the same shape as the endpoint's other 400s.
   - `connect_api_key` calls it right after the `key_data`/`provider` check, so a malformed `options` is rejected for every provider.
   - The OpenAI case calls `connect_openai(parse_api_key(key_data), reasoning_summaries=options.get("reasoning_summaries") is True)`.
   - `connect_openai(key: str, reasoning_summaries: bool)` sets `Config.shared().open_ai_reasoning_summaries = reasoning_summaries` next to the key, after the key check succeeds. A failed check saves neither.

2. **Disconnect endpoint** (same file). The `ModelProviderName.openai` case of `disconnect_api_key` also sets `Config.shared().open_ai_reasoning_summaries = False`.

3. **Schema check.** `payload` stays an untyped `dict`, so the OpenAPI schema doesn't change. Confirm with `app/web_ui/src/lib/check_schema.sh`, using a tkinter stub on `PYTHONPATH` in this sandbox.

4. **Dialog** (`app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte`), built with the `kiln-ui` skill.
   - New type and `Provider` field:

     ```ts
     type ApiKeyOption = { id: string; label: string; info: string }
     // in Provider:
     api_key_options?: ApiKeyOption[]
     ```

   - The OpenAI entry gets one option: `id: "reasoning_summaries"`, `label: "Show reasoning summaries (requires Org verification)"`, and `info` with the text from architecture §3.10 (the verification link as a markdown link, which `InfoTooltip` renders).
   - New state `let api_key_option_values: Record<string, boolean> = {}`. `show_api_key_dialog` sets it to every option of the opened provider mapped to `false`, so the checkbox always starts unchecked and the body always carries an explicit boolean.
   - Render the options below the fields-and-Connect row and above the Cancel link, outside `#api-key-fields` (which `submit_api_key` reads as text inputs). Each option is the house checkbox, `FormElement` with `inputType="checkbox"`, `label={option.label}`, `info_description={option.info}`, and `bind:value={api_key_option_values[option.id]}`. `FormElement` owns the `<input>`, the label and the `InfoTooltip`, so the route file writes none of them. One wrapper div owns the spacing (`pt-4`, matching the warning's wrapper in the same dialog).
   - `submit_api_key` adds `options: api_key_option_values` to the POST body.

5. **Maintainer skill** (`.agents/skills/claude-maintain-models/SKILL.md`, "Provider Quirks Reference" → OpenAI). Add a bullet: set `openai_reasoning_summary="auto"` on the OpenAI-direct provider of GPT-5.4+ and GPT-6+ reasoning models; the value is sent to OpenAI as `reasoning.summary` as-is; Kiln only sends it when the user turned on reasoning summaries when connecting OpenAI; leave it unset on OpenRouter and other providers.

6. **Docs sync.** Run the `docs-sync` skill over `origin/main...` plus this phase's working tree. Known stale item: the "What is known: LiteLLM" section of `specs/research/openai-responses-api/handoff_reasoning_across_turns.md` still names 1.106.6 as the upgrade target; the shipped target is 1.105.6. Fix every stale hit in place.

7. **Checks.** `uv run ./checks.sh --agent-mode`, the conventions gate (`--worktree`), and the `kiln-ui` gate (`--worktree`).

## Tests

Desktop (`app/desktop/studio_server/test_provider_api.py`). The new tests use the real `Config` on the temp settings file from the root `conftest.py`, and patch only `requests.get`:

- `test_connect_openai_saves_reasoning_summaries_option` (parametrized: options `{"reasoning_summaries": True}` → `True`, `{"reasoning_summaries": False}` → `False`, no `options` → `False`): connecting saves the key and the setting.
- `test_connect_openai_without_option_turns_reasoning_summaries_off`: with the setting already `True`, connecting with no options leaves it `False`.
- `test_connect_openai_failed_key_check_saves_nothing` (parametrized over a 401 and a request exception): with options true, neither the key nor the setting is saved.
- `test_connect_api_key_rejects_invalid_options` (parametrized: a list, a string, `null`, a non-bool value, for OpenAI and for one other provider): 400 with `{"message": "Invalid options"}`, and the provider's connect function isn't called.
- `test_disconnect_api_key_openai_turns_reasoning_summaries_off`: with key and setting saved, disconnect clears the key and sets the setting to `False`.
- Update `test_connect_api_key_openai_success` to expect `connect_openai("test_key", reasoning_summaries=False)`, and add a case that passes `options` through to `reasoning_summaries=True`.
- Update `test_disconnect_api_key_openai` (mocked config) to assert the setting is `False`.

Web (`connect_providers.test.ts`):

- `shows the reasoning summaries option, unchecked, in the OpenAI dialog`: the checkbox labelled "Show reasoning summaries (requires Org verification)" is present and unchecked, and the tooltip text names organization verification.
- `does not show the reasoning summaries option for other providers`: the OpenRouter dialog has no such checkbox.
- `sends the reasoning summaries option with the OpenAI key`: checking the box and connecting posts `options: { reasoning_summaries: true }`; not checking it posts `{ reasoning_summaries: false }`.
- `starts the option unchecked when the dialog is reopened`: check it, cancel, reopen, and it is unchecked.
- Update the Cloudflare body assertions to include `options: {}`.
