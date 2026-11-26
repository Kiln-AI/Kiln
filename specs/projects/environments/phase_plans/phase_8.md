---
status: complete
---

# Phase 8: Reset Argument Forms

## Overview

When an OpenEnv server publishes a JSON schema for its reset arguments, the Environment Option dialog shows a form built from it, with a Raw JSON toggle back to the JSON editor. The schema is read fresh each time the dialog opens: from the `reset` key of `GET /schema`, falling back to `GET /seahaven/schemas`. Nothing new is stored.

## Steps

1. `libs/core/kiln_ai/openenv/session_manager.py`: add `OpenEnvSessionManager.reset_schema(openenv_server) -> dict[str, JsonValue] | None`. One `httpx.AsyncClient(timeout=CONNECT_TIMEOUT_S)`. A module helper `_reset_schema_at(client, openenv_server, base_url, path)` returns the `reset` object of the body at `path`, or None for a non-2xx answer, a non-JSON body, or no `reset` object; it raises `OpenEnvError` ("... which did not answer {path}: ...") on `httpx.TransportError`. Try `/schema`, then the Seahaven fallback `/seahaven/schemas` in one commented block. No url raises `OpenEnvError` with the existing no-url text, moved into `_no_url_message` and shared with `_server_for`.
2. `libs/core/kiln_ai/openenv/testing.py`: `serve_in_thread(extra_routes=...)` serves extra JSON bodies by path.
3. `app/desktop/studio_server/openenv_server_api.py`: `OpenEnvServerResetSchemaResponse { reset_schema: dict[str, Any] | None }` and `GET /api/projects/{project_id}/openenv_servers/{openenv_server_id}/reset_schema` (tag "OpenEnv Servers", `ALLOW_AGENT`). 400 with the tools route's no-url message (shared via `_require_url`), 502 on `OpenEnvError` or `ValueError`. Add the agent-check annotation file, regenerate `api_schema.d.ts`.
4. `app/web_ui/src/lib/types.ts`: no new alias needed beyond what the API helper returns. `lib/api/openenv_server_api.ts`: `load_openenv_server_reset_schema(project_id, openenv_server_id) -> Promise<Record<string, unknown> | null>`.
5. `app/web_ui/src/lib/utils/openenv_reset_schema.ts` (new, pure):
   - `reset_schema_to_form_schema(schema: unknown): JsonSchemaProperty | null`: resolves local `#/$defs/` refs (missing or cyclic returns null), collapses `anyOf: [X, {type: "null"}]` to X and drops the property from `required`, keeps `title`, `description`, `enum`, `type`, `properties`, `required`; drops `default`, `additionalProperties: false` and validation-only keywords. Returns null on any other `anyOf`, `oneOf`, `allOf`, `const`, a `type` list, a missing type, an array, an object with no `properties`, or `additionalProperties` other than false. The root must be an object.
   - `kwargs_fit_form(kwargs, form_schema): { fits: true } | { fits: false; reason: string }`: every key is a known property and every value matches its type or enum, recursively. `null`, an empty string and an empty nested object don't fit, because the form would drop them.
   - `form_value_to_kwargs(value): Record<string, JsonValue>`: drops `""`, `undefined`, `null`, and objects left empty, recursively; the root stays an object.
6. Shared-component change, its own commit: `run_input_form.svelte` gains `set_structured_input_data(value)`, which remounts the structured form with that value. `run_input_form_element.svelte`, `run_input_form_element_ref_capture.svelte` and `run_input_array_element.svelte` gain an opt-in `initial_value: unknown = undefined` prop passed down the tree. A pure helper `initial_field_value(property, value)` in `lib/components/run_input_initial_value.ts` gives a scalar field's form value (enum values as-is, booleans as `"true"`/`"false"`, generic objects as formatted JSON). Without a call to the new method, every caller renders as before.
7. `environment_option_dialog.svelte`:
   - Takes `project_id` and `openenv_server_id` (passed from `+page.svelte`). On open, load the reset schema (request counter guards a reopen), convert it; an error or null means no schema.
   - Draft state gains a view: JSON editor while loading and with no schema. When a form schema arrives and the editor text is unchanged since open: parse it, and if the args fit, show the form prefilled; otherwise stay on Raw JSON. If the user has typed, stay on Raw JSON.
   - With a schema: the Reset Arguments header gets the schema description from the Copy table and an `inline_action` toggle at the right of its label row ("Raw JSON" while the form shows, "Form" while the JSON editor shows). Form to JSON: build the form's value (an error shows as the form error), clean it with `form_value_to_kwargs`, format it into the editor. JSON to form: parse; invalid JSON or kwargs that don't fit set the form error ("The form can't show these reset arguments: [reason]. Edit them as JSON.") and the editor stays.
   - Save while the form shows: build the form value, clean it, and save it with the existing `options_with_draft` by formatting it into the draft text.
   - Flow logic (choosing the opening view, the two toggle directions, save from the form) lives in `openenv_server_detail.ts` (or a sibling `.ts`) with unit tests; the `.svelte` file only wires it.

## Tests

- `test_session_manager.py`, `TestResetSchema`: `/schema` with `reset` returns it; `/schema` with no `reset` falls back to `/seahaven/schemas`; neither (404 fallback) returns None; a non-object `reset` is treated as none; an unreachable URL raises `OpenEnvError` naming `/schema`; no url raises `OpenEnvError`.
- `test_openenv_server_api.py`: reset_schema endpoint with no url is 400; `OpenEnvError` is 502; a null schema and a schema are returned as `reset_schema`.
- `openenv_reset_schema.test.ts`: the Seahaven reset schema shape converts (nullable `anyOf` collapsed, `$ref` into `$defs` resolved with outer description kept, enums kept, defaults dropped, not required); each unsupported construct (other `anyOf`, `oneOf`, `allOf`, `const`, type list, no type, array, free-form object, missing ref, cyclic ref, non-object root) returns null; `kwargs_fit_form` true cases (empty, nested, enum, integer) and false cases (unknown key, wrong type, non-integer, enum miss, null, empty string, empty object) with reasons; `form_value_to_kwargs` drops empty values recursively.
- `run_input_initial_value.test.ts`: scalar conversions.
- A component test that `run_input_form`'s `set_structured_input_data` prefills nested fields, and that `get_structured_input_data` reads them back.
- Dialog flow unit tests: opening view for add, edit that fits, edit that doesn't fit, typed-before-load; toggle round trip; toggle refused with reason on invalid JSON and on non-fitting JSON; save from the form drops empty fields.
- A dialog component test: no schema shows the editor and no toggle; a schema shows the form; an edit that doesn't fit opens on Raw JSON.
