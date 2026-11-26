---
status: complete
---

# Phase 12: Probe the API through the MCP; fix unclear errors and add route descriptions

## Overview

Build step 8 (architecture section 10; functional spec section 11). The probe ran before this plan was written, against the seeded sandbox project (`.agents/scripts/playwright_server.sh start`, backend on port 6545), through the real `/mcp` endpoint with the SDK's `streamablehttp_client`. It walked the seed list, then every operation of the API reference: for each, all ids wrong; real project and task ids with the other ids wrong; a body that is not JSON and an empty body where the schema has required fields; a GET without its required query parameters; and one GET that should work for every GET whose ids are only the project and task. DELETE was only ever called with wrong ids. The findings and their fixes are the table below; each fix is made where the message is raised, so every API client gets it.

The second half is route descriptions. Of the 243 operations that are not MCP-blocked, 173 have no `description`, and 10 more have a first sentence longer than the 100 characters the generator keeps in a catalogue row, or one that does not say what the endpoint does (`Proxy to Kiln Copilot ...`, `For multi-turn tasks, only leaf TaskRuns ...`). Each gets a handler docstring whose first sentence says what the endpoint does, in words an agent can choose by, in at most 100 characters. The `summary` stays a short name. The response models of the model info endpoints get the class docstrings and `Field` descriptions that phase 4 left out.

Not in scope: the texts of `api_tool/messages.py` (backlog B2) and the wrong-method text (B3), which are open owner decisions. MCP-blocked routes need no description.

## Probe findings

The bar (architecture section 10): an error says what is wrong, names the field or the id, and says what to do next.

| # | Endpoint(s) | Old message | Fix |
|---|---|---|---|
| 1 | Every route that looks up an object by id (project, task, run, feedback, spec, prompt, eval, eval config, eval input, run config, eval run, document, extractor, chunker, embedding, vector store and RAG configs, tool server, code tool, skill, OpenEnv server, data gen batch job, job, finetune) | `Project not found. ID: x` (no next step); `Extractor config not found`, `Document not found`, `RAG config not found`, `Tool server not found`, `Code tool not found`, `Skill not found`, `OpenEnv server not found`, `Batch job not found`, `Prompt not found` (no id); `Job not found: x`, `Finetune with ID 'x' not found`, `Document x not found`, `Embedding config x not found` (mixed shapes) | One shape from one helper, `kiln_server.custom_errors.not_found_error(kind, item_id, plural)`: `Project not found. ID: x. Check the ID, or list the projects to find the right one.` |
| 2 | Every route with a JSON body, when the body is not JSON | `[0]: JSON decode error` | `Request body is not valid JSON (Expecting value, at character 0). Send a JSON value that matches the endpoint's schema.` |
| 3 | Routes whose body as a whole fails validation (`POST .../runs/delete` with an object, an update with no field set) | `: Input should be a valid list`; `: Value error, At least one field must be provided` | An empty location becomes `Request body`; pydantic's `Value error, ` and `Assertion failed, ` prefixes are dropped from `message` and `error_messages` (kept in `source_errors`) |
| 4 | `POST .../tasks/{task_id}/run` with `plaintext_input` on a task with an input schema (and the reverse) | `No input provided. Ensure you provided the proper format (plaintext or structured).` | Says which field this task reads: `This task has an input schema, so its input goes in structured_input, as a JSON object that matches the schema.` / `This task takes plain text input, so its input goes in plaintext_input.` |
| 5 | Any run on a model whose provider is not connected (`POST .../run`, and every path through `check_provider_warnings`) | 500, `Attempted to use OpenAI without an API key set. \nGet your API key from ...` | `ProviderNotConnectedError(ValueError)` in `provider_tools`, raised by `check_provider_warnings` and the Cloudflare config, with the sentence `Connect it in the Kiln app under Settings > AI Providers, or choose a model from a connected provider.` appended; `custom_errors` maps it to 400 |
| 6 | Any body with a `prompt_id` of no known form | `Invalid prompt ID: x` | Lists the forms: `Use a saved prompt's ID (id::<prompt_id>), a run config's prompt, a fine-tune's prompt, or a prompt generator: simple_prompt_builder, ...` |
| 7 | `PATCH`/`DELETE .../prompts/{prompt_id}` with an id that is not `id::...` | `Only custom prompts can be updated. Automatically frozen prompts can not be edited or deleted.` (also for an id that is no prompt at all) | Names the id and the form: `Prompt x can't be edited or deleted. Only custom prompts, whose IDs start with id::, can be: generators and frozen prompts are fixed because evals depend on them.` |
| 8 | `POST /api/jobs/{type}` with an unknown type | `Unknown job type: x` | Lists the registered types (`JobRegistry.type_names()`) |
| 9 | `POST /api/jobs/wait` with a misspelt field (`job_ids`) | 200 `[]` at once, so the caller believes the jobs are done | `WaitForJobsRequest` forbids extra fields: a 422 names the field |
| 10 | Every Kiln Copilot route without a key (`/api/chat/...`, `/api/copilot/...`, `/api/check_entitlements`, data guide jobs) | `Kiln Copilot API key not configured. Please connect your API key in settings.` | `This needs Kiln Pro, which is not connected. Connect it in the Kiln app under Settings > AI Providers > Kiln Pro.` |
| 11 | `GET /api/finetune/hyperparameters/{provider_id}`, `POST .../finetunes` with an unknown provider | `Fine tune provider 'x' not found` | Lists the fine-tune providers |

Left as is:

- `GET /api/settings/{item_id}` with an unknown key answers `{"x": null}`: an unset setting and an unknown one look the same, and the settings file is open-ended.
- `GET /api/jobs/{id}/errors` for an unknown job answers `[]`: the route is a documented best-effort read that never errors.
- Field names in 422 messages are capitalised (`Model_name: Field required`) for the web UI; `source_errors` keeps the exact `loc`, so the field is named.
- An invalid Kiln Pro key: the Kiln server's own message is passed through (`check_response_error`); it cannot be probed offline.
- `No memory with id 'x' in this store.` (memory API's domain error), `Tool not found or could not be instantiated: ...`, `Request timed out. Please try again.`: clear enough.
- MCP-level texts (blocked endpoint, path not allowed, no endpoint matches): clear. B2 and B3 are owner decisions.

## Steps

1. **`not_found_error`** in `libs/server/kiln_server/custom_errors.py`:

   ```python
   def not_found_error(kind: str, item_id: str, plural: str) -> HTTPException:
       """A 404 naming the missing object and how to find the right ID."""
   ```

   Use it at every site of finding 1 (the shared `*_from_id` lookups of `project_api`, `task_api`, `run_api`, `feedback_api`, `spec_api`, `prompt_api`, `eval_api`, `copilot_utils`, `document_api`, `code_tool_api`, `tool_api`, `skill_api`, `openenv_server_api`, `data_gen_api`, `finetune_api`, and `jobs/api.py`'s `JobNotFoundError` mapping). Messages that already name the object differently stay where they carry more (for example `Parent run not found`).

2. **Validation text** in `custom_errors.validation_exception_handler`: a helper `_error_message(error) -> str` that handles `json_invalid` (finding 2), the empty location and the pydantic prefixes (finding 3).

3. **`run_task`** input text (finding 4), in `libs/server/kiln_server/run_api.py`.

4. **`ProviderNotConnectedError`** (finding 5) in `libs/core/kiln_ai/adapters/provider_tools.py`, and its 400 handler in `custom_errors`.

5. **Prompt texts** (findings 6, 7): `libs/core/kiln_ai/datamodel/prompt_id.py`, `libs/server/kiln_server/prompt_api.py`.

6. **Jobs** (findings 8, 9): `JobRegistry.type_names()`, the unknown-type text, `model_config = ConfigDict(extra="forbid")` on `WaitForJobsRequest`.

7. **Kiln Pro text** (finding 10) in `app/desktop/studio_server/utils/copilot_utils.py`; **fine-tune provider text** (finding 11) in `finetune_api.py`.

8. **Route descriptions.** A handler docstring for each of the 173 operations without a description, and a rewritten first sentence for the 10 named in the overview. Rules: the first sentence says what the endpoint does and is at most 100 characters; further sentences add what an agent needs to call it right (ids it takes, what it returns, side effects, long-running behaviour) and nothing that the parameter and field docs already say; no history; plain ASCII punctuation.

9. **Model info models.** Class docstrings on `ModelInfoProviderEntryRow`, `ModelInfoProviderEntryDetails`, `ModelInfoProviderRow`; `Field` descriptions on `display_name`, `deprecated`, `default_thinking_level`.

10. **Regenerate**: `make api_docs`, `make schema` (`api_schema.d.ts`). The agent-policy annotations carry no descriptions, so `make annotations` changes nothing; it is run to confirm.

11. **Tests** and updates of the tests that assert the old texts.

## Tests

- `app/desktop/studio_server/test_route_descriptions.py`:
  - `test_every_unblocked_route_has_a_description`: every operation of `make_app().openapi()` without an MCP deny has a non-empty `description`.
  - `test_every_description_starts_with_a_short_sentence`: its first sentence is at most 100 characters.
  - `test_blocked_routes_are_not_checked`: the helper that lists the operations to check leaves out an operation carrying `x-mcp-policy` deny.
- `libs/server/kiln_server/test_custom_error.py`:
  - `test_not_found_error`: status 404 and the full text.
  - `test_invalid_json_body_message`, `test_body_level_error_says_request_body`, `test_value_error_prefix_is_dropped` (with `source_errors` unchanged).
  - `test_provider_not_connected_is_400`.
- `libs/core/kiln_ai/adapters/test_provider_tools.py`: `check_provider_warnings` raises `ProviderNotConnectedError`, still a `ValueError`, whose text ends with the connect sentence; the Cloudflare config raises it too.
- `libs/core/kiln_ai/datamodel/test_prompt_id.py`: the invalid-id text lists the generator names.
- `libs/server/kiln_server/test_prompt_api.py`: the non-custom id text names the id.
- `libs/server/kiln_server/test_run_api*.py`: the two input texts.
- `app/desktop/studio_server/jobs/test_*`: the unknown-type text lists the types; `POST /api/jobs/wait` with `job_ids` is a 422; `type_names()`.
- `app/desktop/studio_server/utils/test_copilot_utils.py` (or the existing test of `get_copilot_api_key`): the Kiln Pro text.
- `test_finetune_api.py`: the provider text lists providers.
- Existing tests that assert the old not-found texts are updated to the new ones.
