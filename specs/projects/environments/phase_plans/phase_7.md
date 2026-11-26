---
status: complete
---

# Phase 7: OpenEnv on the run page and conversation page

## Overview

Lets a user pick an Environment Option on the run page and see which OpenEnv a run used. The run page gains the Environment Options field (hidden unless the selected tools reach an OpenEnv), and sends the chosen option's reset arguments as `env_reset_kwargs`. The multi-turn composer sends them on the first turn only. The tool picker keeps an offline OpenEnv's selected tools. Runs show an "OpenEnv" property list. The conversation page disables Fork in a conversation with an OpenEnv, and shows session errors as a Warning above the composer. The shared-control changes are opt-in and each will be its own commit.

## Steps

1. Shared controls (each opt-in; defaults render as before)
   - `lib/ui/fancy_select_types.ts`: `Option.description_preformatted?: boolean`. `lib/ui/fancy_select.svelte`: when true, the description renders `font-mono whitespace-pre-wrap` with no `line-clamp`.
   - `lib/ui/trace/chat_message_actions.svelte`: `fork_disabled_reason: string | null = null`. When set, Fork renders disabled inside a DaisyUI `tooltip` wrapper whose `data-tip` is the reason. `lib/ui/trace/chat_trace.svelte` gains the same prop and passes it to every assistant turn's actions.
   - `lib/services/multiturn_send.ts`: `RunConfigController.get_env_reset_kwargs?: () => Promise<ResetKwargs | null>`; a root turn (no parent) sends its result as `env_reset_kwargs`; later turns never send it. Failures return the HTTP `status`.
   - `lib/ui/conversation/multiturn_composer.svelte`: `warning_error_statuses: number[] = []`. A send that fails with one of these statuses shows the server's message in an error `Warning` above the form instead of the form's error line; the next send clears it.

2. Tool picker: `tools_selector.svelte` `drop_unselectable_tools` keeps ids for which `is_environment_tool_id` (`lib/utils/environments.ts`, prefix `kiln_tool::env::`) is true.

3. API and helpers
   - New `lib/api/environments_api.ts`: `load_environment(project_id, environment_id)` (moved from the detail page's `environment_detail.ts`, which re-exports it) and `lookup_run_environment(project_id, task_id, tool_ids)` (POST `run_environment`).
   - `lib/types.ts`: `RunEnvironment` alias for `RunEnvironmentResponse`, `EnvironmentEpisode`.
   - `lib/utils/environments.ts`: `is_environment_tool_id`, `environment_detail_link(project_id, environment_id)`, and the field's pure logic: `environment_field_state(response)` -> `hidden | error | empty | options`, `environment_option_groups(environment)` (one group; value = option name; description = formatted reset arguments, preformatted), `selected_option_after_change(environment, previous_name)` (keep the name if it still exists, else the first), `reset_kwargs_for(environment, name)`.

4. Environment Options field: new `lib/ui/run_config_component/environment_options_field.svelte`
   - Props `project_id`, `task_id`, `tool_ids`. Debounces `lookup_run_environment` by 250 ms on tool change and ignores stale replies; a failed lookup shows its message as the error state.
   - Renders per state: nothing; label (`header_only` FormElement with `error_message`) plus a `text-sm text-error` line; `fancy_select` with empty options, `empty_label="None"`, empty state "No Environment Options" / "Add Environment Options" linking to the detail page; `fancy_select` of options with the first selected.
   - `info_description`: "Sets the OpenEnv's starting data for this run, such as the company and the user the agent acts as."
   - Exports `async get_env_reset_kwargs()`: flushes a pending lookup, awaits it, returns the selected option's kwargs or null.

5. `run_config_component.svelte`: prop `show_environment_options = false`; when true (and not an MCP run config) renders the field between Skills and Advanced Options with `tool_ids = [...tools, ...skills]`. Exports `get_env_reset_kwargs()` (null when the field isn't shown).

6. Run page (`routes/(app)/run/+page.svelte`): both layouts pass `show_environment_options={true}`; the single-turn Run adds `env_reset_kwargs` to the `/run` body when non-null. The multi-turn composer gets it through the controller.

7. Run sidebar (`lib/ui/run_sidebar.svelte`): when `run.env_episode` is set, a `PropertyList` titled "OpenEnv" after Usage: OpenEnv (the environment's name, loaded by id, falling back to the id; links to the detail page) and Reset Arguments (custom slot, 2-space JSON in a `pre`). Covers single-turn output and the conversation page sidebar.

8. Conversation page (`dataset/.../[run_id]/run/+page.svelte`): when `run.env_episode` is set, pass `fork_disabled_reason` "This conversation uses an OpenEnv, so it can only continue from the latest turn." to ChatTrace, and `warning_error_statuses={[409]}` to the append composer.

## Tests

- `fancy_select` (new `fancy_select.test.ts`): a preformatted description renders unclamped with `whitespace-pre-wrap`; a plain description keeps `line-clamp-3`.
- `chat_message_actions` (new test): no reason renders an enabled Fork; a reason renders it disabled with the tooltip text.
- `multiturn_send.test.ts`: a root turn sends `env_reset_kwargs` from the controller; null is not sent; a later turn never sends it; failure carries status.
- `multiturn_composer.test.ts`: a 409 in `warning_error_statuses` shows the Warning and not the form error; other statuses keep the form error.
- `tools_selector.test.ts`: a persisted `kiln_tool::env::` id survives when its environment isn't in `available_tools`; a non-env unavailable id is still dropped.
- `environments.test.ts`: `is_environment_tool_id`; each `environment_field_state` result; option groups (order, preformatted description); `selected_option_after_change`; `reset_kwargs_for`.
- `environments_api.test.ts`: `lookup_run_environment` posts the tool ids and returns the body; throws on error.
- `environment_options_field.test.ts`: hidden with no environment; error line; empty state; options with first selected and `get_env_reset_kwargs` returning its kwargs; lookup debounced (one call for rapid changes); stale reply ignored.
- `run_sidebar` test: OpenEnv list shown with name link and reset arguments when `env_episode` is set; absent otherwise.
