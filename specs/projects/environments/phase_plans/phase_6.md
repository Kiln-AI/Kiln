---
status: complete
---

# Phase 6: OpenEnv pages in the Tools area

## Overview

Gives OpenEnv environments a home next to MCP servers: rows on the Tools list, an "OpenEnv" item on Add Tools, a Connect OpenEnv page, and an OpenEnv detail page with the Edit OpenEnv dialog and the Environment Option dialog (add, edit, clone, remove). Adds the opt-in shared-component changes those screens need. The detail page's Version property needs the server's reported `name@version`, which no endpoint returns yet, so this phase adds one small read-only endpoint for it.

## Steps

1. Server: `app/desktop/studio_server/environment_api.py`
   - `EnvironmentVersionResponse(env_version: str)`.
   - `GET /api/projects/{project_id}/environments/{environment_id}/version` (`ALLOW_AGENT`): `refresh(env)` then `env_version(env)` on the shared session manager; `OpenEnvError`/`ValueError` -> 502 with the message; missing environment -> 404.
   - Annotation file `get_api_projects_project_id_environments_environment_id_version.json`; regenerate `api_schema.d.ts`.

2. Shared components (each opt-in; defaults render as before)
   - `lib/components/code_editor.svelte`: `language: "python" | "json" = "python"`, loaded through new `lib/components/code_editor_language.ts` `load_language_extension(language)`, which imports `@codemirror/lang-json` only for JSON. Add `@codemirror/lang-json` to `package.json`.
   - `lib/ui/error_details_block.svelte`: `full_width = false`; true drops `max-w-[600px] mx-auto`.
   - `lib/ui/settings_item.svelte` + `kiln_section.svelte` + `kiln_section_types.ts`: optional `link_label`, `link_href`, rendered after the description as `<a class="link" target="_blank">`. A row with a link renders as `div role="button" tabindex=0` (Enter/Space run the action) because a link can't be nested in a `<button>`; the link stops propagation.
   - `lib/ui/edit_dialog.svelte`: forward its Dialog's `close` event, so a page can mount it only while open.

3. Shared web helpers
   - `lib/types.ts`: `Environment`, `EnvironmentTool`, `NamedResetKwargs` aliases.
   - `lib/utils/environments.ts`: `OPENENV_DOCS_URL`, `SEAHAVEN_URL`, `OPENENV_FIELDS` (field copy shared by Connect and Edit), `format_reset_arguments` (2-space JSON), `parse_reset_arguments` (blank -> `{}`, invalid JSON / non-object -> the Copy-table errors).
   - `lib/utils/tool_arguments.ts` `format_tool_arguments(schema)` and `lib/components/tool_arguments_list.svelte`, extracted from the tool server page, which now uses them.
   - `lib/ui/icons/wrench_icon.svelte`.

4. Tools list (`tools/[project_id]/+page.svelte`): load `GET /environments`; one row per environment (Type "OpenEnv", Status "Ready" success Warning), click -> detail page; counts toward "not empty".

5. Add Tools: "OpenEnv" item in Custom Tools with the "Learn more" link and "Connect" -> `add_tools/openenv`.

6. Connect OpenEnv (`add_tools/openenv/+page.svelte`, `+page.ts`): AppPage with Read the Docs; Kiln Seahaven `Callout` (wrench icon, Learn More opens GitHub in a new tab) in `mb-8 max-w-4xl`; `FormContainer submit_label="Connect"` with Name, Description, Server URL; server error in the form's error line; on success uncache available tools and go to the detail page.

7. OpenEnv detail (`environments/[environment_id]/`)
   - `environment_detail.ts`: API wrappers (`load_environment`, `load_environment_tools`, `load_environment_version`, `save_environment_options`) and pure list logic (`blank_draft`, `draft_from`, `clone_draft`, `options_with_draft`, `options_without`).
   - `environment_option_dialog.svelte`: Dialog titled Add/Edit Environment Option; form mounted only while open; Name + Reset Arguments (header_only FormElement over CodeEditor json, 160px); parse errors and server errors in the form error line; Save PATCHes the whole list.
   - `+page.svelte`: AppPage "OpenEnv" / "Name: X", Edit button; Properties and Connection Details PropertyLists (Version shows "Can't reach OpenEnv" in error style when the version call fails); Environment Options header copied from Run Configurations, table with Name, Reset Arguments (formatted JSON) and TableActionMenu (Edit, Clone, Remove), empty message in the table frame; Available Tools table, or a full-width ErrorDetailsBlock "Can't Reach OpenEnv" when offline. Edit OpenEnv is an `EditDialog` mounted only while open; saving uncaches available tools and reloads without the spinner.

## Tests

- `test_environment_api.py` `TestVersion`: reports `name@version`; re-reads after the server restarts with a new version; unreachable -> 502; no env_url -> 502; unknown environment -> 404.
- `environments.test.ts`: formatting, blank/empty object, invalid JSON, each non-object JSON, round trip.
- `tool_arguments.test.ts`: required/optional, Unknown type, non-object property schemas skipped, schemas without properties.
- `environment_detail.test.ts`: drafts (blank, edit, clone name), append/replace/trim/blank, both error kinds, input list unchanged, remove by index, each API wrapper's path and body, error propagation.
- `settings_item.test.ts`: no link renders a button as before; label without href ignored; link attributes; div with button role; click/Enter/Space run the action; clicking the link doesn't.
- `error_details_block.test.ts`: default centred width; `full_width` drops it.
- `code_editor_language.test.ts`: Python by default path, JSON loads lang-json.
- `edit_dialog.test.ts`: forwards the dialog's close event.
