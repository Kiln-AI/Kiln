<script lang="ts">
  // Shared "Generation Options" block for the input data guide setup + refine
  // flows. Two display modes:
  //   - "tiles" (default): a single compact clickable tile for the input
  //     generation stage.
  //   - "link": no inline UI; parent renders its own trigger and calls
  //     open_combined_dialog() to launch the input config dialog.
  //
  // Parents read the resulting config via get_input_run_config().
  import { onMount } from "svelte"
  import type { Task } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import {
    available_models,
    load_available_models,
    model_info,
    load_model_info,
    model_name as friendly_model_name,
  } from "$lib/stores"
  import type { AvailableModels, RunConfigProperties } from "$lib/types"

  export let project_id: string
  // Optional — Task is currently unused but kept on the API for parity with the
  // copilot variant that needs it for run-config presets.
  export let task: Task | null = null
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  $: void task
  export let mode: "tiles" | "link" = "tiles"

  let input_config_dialog: Dialog
  let combined_config_dialog: Dialog
  let input_run_config_component: RunConfigComponent | null = null
  let input_model_name: string = ""

  function pick_data_gen_model(providers: AvailableModels[]): string | null {
    for (const provider of providers) {
      for (const m of provider.models) {
        if (
          m.suggested_for_data_gen &&
          m.supports_structured_output &&
          m.supports_data_gen &&
          !m.deprecated &&
          !m.untested_model
        ) {
          return `${provider.provider_id}/${m.id}`
        }
      }
    }
    return null
  }

  // Initial recommended model. Without this RunConfigComponent falls back to
  // ui_state.selected_model (the user's last pick anywhere in the app), which
  // is not what we want for an SDG defaulted page.
  let recommended_data_gen_model: string | null = null
  $: if (!recommended_data_gen_model && $available_models.length > 0) {
    recommended_data_gen_model = pick_data_gen_model($available_models)
  }

  onMount(() => {
    load_available_models()
    load_model_info()
  })

  function open_input_config_dialog() {
    input_config_dialog?.show()
  }

  export function open_combined_dialog() {
    combined_config_dialog?.show()
  }

  export function get_input_run_config(): RunConfigProperties | null {
    return (
      input_run_config_component?.run_options_as_run_config_properties() ?? null
    )
  }
</script>

{#if mode === "tiles"}
  <div class="flex flex-row flex-wrap gap-2">
    <button
      type="button"
      class="text-left rounded-md border bg-white px-3 py-2 hover:border-primary hover:shadow-sm transition-all min-w-[180px]"
      on:click={open_input_config_dialog}
    >
      <div
        class="text-[10px] text-gray-500 uppercase font-medium tracking-wide"
      >
        Input Generation Options
      </div>
      <div class="mt-0.5 text-xs truncate">
        Model: {input_model_name
          ? friendly_model_name(input_model_name, $model_info)
          : "—"}
      </div>
      <div class="text-xs text-gray-400 leading-none">…</div>
    </button>
  </div>

  <Dialog
    bind:this={input_config_dialog}
    title="Input Generation Options"
    sub_subtitle="Configure the run options used to generate example inputs."
    action_buttons={[{ label: "Done", isPrimary: true }]}
  >
    <RunConfigComponent
      bind:this={input_run_config_component}
      bind:model_name={input_model_name}
      model={recommended_data_gen_model}
      {project_id}
      requires_structured_output={true}
      show_name_field={false}
      hide_prompt_selector={true}
      show_tools_selector_in_advanced={true}
      model_dropdown_settings={{
        requires_data_gen: true,
        suggested_mode: "data_gen",
      }}
    />
  </Dialog>
{:else}
  <Dialog
    bind:this={combined_config_dialog}
    title="Generation Options"
    sub_subtitle="Options used to generate synthetic inputs."
    width="wide"
    action_buttons={[{ label: "Done", isPrimary: true }]}
  >
    <div class="flex flex-col gap-6">
      <div>
        <div class="font-medium">Input Generation Options</div>
        <RunConfigComponent
          bind:this={input_run_config_component}
          bind:model_name={input_model_name}
          model={recommended_data_gen_model}
          {project_id}
          requires_structured_output={true}
          show_name_field={false}
          hide_prompt_selector={true}
          show_tools_selector_in_advanced={true}
          model_dropdown_settings={{
            requires_data_gen: true,
            suggested_mode: "data_gen",
          }}
        />
      </div>
    </div>
  </Dialog>
{/if}
