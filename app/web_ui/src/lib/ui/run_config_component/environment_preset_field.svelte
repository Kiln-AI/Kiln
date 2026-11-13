<script lang="ts">
  import { onDestroy } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { lookup_run_openenv_server } from "$lib/api/openenv_server_api"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import {
    openenv_server_detail_link,
    environment_preset_field_state,
    environment_preset_groups,
    reset_kwargs_for,
    selected_preset_after_change,
    type EnvironmentPresetFieldState,
    type ResetKwargs,
  } from "$lib/utils/openenv"

  export let project_id: string
  export let task_id: string | null
  // Every tool id the run would use, saved or not yet saved.
  export let tool_ids: string[]

  const LOOKUP_DEBOUNCE_MS = 250
  const LABEL = "Environment Preset"
  const INFO =
    "Sets the OpenEnv server's starting data for this run, such as the company and the user the agent acts as."

  let field_state: EnvironmentPresetFieldState = { kind: "hidden" }
  let selected_preset: string | null = null
  let selected_openenv_server_id: string | null = null

  let scheduled_key: string | null = null
  let latest_request = 0
  let debounce_timer: ReturnType<typeof setTimeout> | undefined
  let scheduled_lookup: (() => Promise<void>) | null = null
  let in_flight: Promise<void> | null = null
  // Set while the newest lookup has failed, so Run can't reset the OpenEnv
  // server with arguments the user never chose.
  let failed_lookup: { error: KilnError; retry: () => Promise<void> } | null =
    null

  $: schedule_lookup(project_id, task_id, tool_ids)

  function schedule_lookup(
    project_id: string,
    task_id: string | null,
    tool_ids: string[],
  ) {
    // The parent hands over a new array whenever it reassigns its tools, even
    // when they haven't changed.
    const key = JSON.stringify([project_id, task_id, tool_ids])
    if (key === scheduled_key) {
      return
    }
    scheduled_key = key
    clearTimeout(debounce_timer)
    const request = ++latest_request
    if (!task_id || tool_ids.length === 0) {
      scheduled_lookup = null
      apply_state(request, { kind: "hidden" })
      return
    }
    const ids = [...tool_ids]
    scheduled_lookup = () => run_lookup(request, project_id, task_id, ids)
    debounce_timer = setTimeout(start_scheduled_lookup, LOOKUP_DEBOUNCE_MS)
  }

  function start_scheduled_lookup() {
    const lookup = scheduled_lookup
    scheduled_lookup = null
    if (lookup) {
      in_flight = lookup()
    }
  }

  async function run_lookup(
    request: number,
    project_id: string,
    task_id: string,
    tool_ids: string[],
  ) {
    try {
      const run_openenv_server = await lookup_run_openenv_server(
        project_id,
        task_id,
        tool_ids,
      )
      apply_state(request, environment_preset_field_state(run_openenv_server))
    } catch (e) {
      const error = createKilnError(e)
      apply_state(request, { kind: "error", message: error.getMessage() })
      if (request === latest_request) {
        failed_lookup = {
          error,
          retry: () => run_lookup(request, project_id, task_id, tool_ids),
        }
      }
    }
  }

  // Replies can arrive out of order; only the newest request's reply counts.
  function apply_state(request: number, next: EnvironmentPresetFieldState) {
    if (request !== latest_request) {
      return
    }
    field_state = next
    failed_lookup = null
    if (next.kind === "presets" || next.kind === "empty") {
      const same_openenv_server =
        next.openenv_server.id === selected_openenv_server_id
      selected_preset = selected_preset_after_change(
        next.openenv_server,
        same_openenv_server ? selected_preset : null,
      )
      selected_openenv_server_id = next.openenv_server.id ?? null
    }
  }

  /**
   * The chosen preset's reset arguments, or null when the tools reach no
   * OpenEnv server, reach more than one, or it has no presets. Waits for a pending
   * lookup, so a Run clicked right after a tool change uses the new tools.
   * A failed lookup is tried once more, and its error thrown if it fails again.
   */
  export async function get_openenv_reset_kwargs(): Promise<ResetKwargs | null> {
    clearTimeout(debounce_timer)
    start_scheduled_lookup()
    await in_flight
    if (failed_lookup) {
      in_flight = failed_lookup.retry()
      await in_flight
    }
    if (failed_lookup) {
      throw failed_lookup.error
    }
    if (field_state.kind !== "presets") {
      return null
    }
    return reset_kwargs_for(field_state.openenv_server, selected_preset)
  }

  onDestroy(() => clearTimeout(debounce_timer))
</script>

{#if field_state.kind === "error"}
  <div>
    <FormElement
      id="environment_preset"
      label={LABEL}
      inputType="header_only"
      info_description={INFO}
      value={null}
    />
    <!-- FormElement has no error line without an input; this matches the
         error line FormContainer shows above its submit button. -->
    <div class="text-sm text-error">{field_state.message}</div>
  </div>
{:else if field_state.kind === "empty"}
  <FormElement
    id="environment_preset"
    label={LABEL}
    inputType="fancy_select"
    info_description={INFO}
    fancy_select_options={[]}
    value={null}
    optional={true}
    hide_optional_badge={true}
    empty_label="None"
    empty_state_message="No Environment Presets"
    empty_state_subtitle="Add Environment Preset"
    empty_state_link={field_state.openenv_server.id
      ? openenv_server_detail_link(project_id, field_state.openenv_server.id)
      : null}
  />
{:else if field_state.kind === "presets"}
  <FormElement
    id="environment_preset"
    label={LABEL}
    inputType="fancy_select"
    info_description={INFO}
    fancy_select_options={environment_preset_groups(field_state.openenv_server)}
    bind:value={selected_preset}
  />
{/if}
