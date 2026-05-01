<script lang="ts">
  // Shared "Generation Options" block for the data guide setup + refine flows.
  // Two display modes:
  //   - "tiles" (default): two compact clickable tiles, one per stage. Each
  //     opens its own dialog. Used by the refine view's footer.
  //   - "link": no inline UI; parent renders its own trigger and calls
  //     open_combined_dialog() to launch a single dialog containing both
  //     stages stacked. Used by the setup form's footer.
  //
  // Parents read the resulting configs via the exposed
  // get_input_run_config() / get_output_run_config() methods.
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
    get_task_composite_id,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { split_tool_and_skill_ids } from "$lib/stores/tools_store"
  import { isKilnAgentRunConfig } from "$lib/types"
  import type { AvailableModels, RunConfigProperties } from "$lib/types"

  export let project_id: string
  // Optional — used by the output dialog to mirror the SDG output flow
  // (prompt + tools/skills at top level, requires_structured_output keyed off
  // task.output_json_schema). Falls back to safe defaults if absent.
  export let task: Task | null = null
  export let mode: "tiles" | "link" = "tiles"

  let input_config_dialog: Dialog
  let output_config_dialog: Dialog
  let combined_config_dialog: Dialog
  let input_run_config_component: RunConfigComponent | null = null
  let output_run_config_component: RunConfigComponent | null = null
  let input_model_name: string = ""
  let output_model_name: string = ""

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

  // Initial recommended model passed into both RunConfigComponents. Without
  // this RunConfigComponent falls back to ui_state.selected_model (the user's
  // last pick anywhere in the app), which is not what we want for an SDG
  // defaulted page.
  let recommended_data_gen_model: string | null = null
  $: if (!recommended_data_gen_model && $available_models.length > 0) {
    recommended_data_gen_model = pick_data_gen_model($available_models)
  }

  // Output-side defaults: pull the user's existing default run config (if the
  // task has one) and forward its non-model run options to the output
  // RunConfigComponent so users don't have to redo their tool/prompt picks for
  // synthetic data gen. The model intentionally stays the SDG-recommended one
  // because SDG benefits from a different model than the task default.
  let output_default_prompt_method: string = "simple_prompt_builder"
  let output_default_tools: string[] = []
  let output_default_skills: string[] = []
  let output_defaults_applied: boolean = false

  $: if (task?.id && task?.default_run_config_id) {
    load_task_run_configs(project_id, task.id)
  }

  $: if (!output_defaults_applied && task?.id && task?.default_run_config_id) {
    const composite = get_task_composite_id(project_id, task.id)
    const configs = $run_configs_by_task_composite_id[composite]
    if (configs) {
      const default_config = configs.find(
        (c) => c.id === task?.default_run_config_id,
      )
      if (
        default_config &&
        isKilnAgentRunConfig(default_config.run_config_properties)
      ) {
        const props = default_config.run_config_properties
        output_default_prompt_method = props.prompt_id
        const split = split_tool_and_skill_ids(props.tools_config?.tools ?? [])
        output_default_tools = split.tool_ids
        output_default_skills = split.skill_ids
      }
      output_defaults_applied = true
    }
  }

  onMount(() => {
    load_available_models()
    load_model_info()
  })

  function open_input_config_dialog() {
    input_config_dialog?.show()
  }

  function open_output_config_dialog() {
    output_config_dialog?.show()
  }

  export function open_combined_dialog() {
    combined_config_dialog?.show()
  }

  export function get_input_run_config(): RunConfigProperties | null {
    return (
      input_run_config_component?.run_options_as_run_config_properties() ?? null
    )
  }

  export function get_output_run_config(): RunConfigProperties | null {
    return (
      output_run_config_component?.run_options_as_run_config_properties() ??
      null
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
    <button
      type="button"
      class="text-left rounded-md border bg-white px-3 py-2 hover:border-primary hover:shadow-sm transition-all min-w-[180px]"
      on:click={open_output_config_dialog}
    >
      <div
        class="text-[10px] text-gray-500 uppercase font-medium tracking-wide"
      >
        Output Generation Options
      </div>
      <div class="mt-0.5 text-xs truncate">
        Model: {output_model_name
          ? friendly_model_name(output_model_name, $model_info)
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

  <Dialog
    bind:this={output_config_dialog}
    title="Output Generation Options"
    sub_subtitle="Configure the run options used to generate example outputs."
    action_buttons={[{ label: "Done", isPrimary: true }]}
  >
    <RunConfigComponent
      bind:this={output_run_config_component}
      bind:model_name={output_model_name}
      model={recommended_data_gen_model}
      prompt_method={output_default_prompt_method}
      tools={output_default_tools}
      skills={output_default_skills}
      {project_id}
      current_task={task}
      requires_structured_output={!!task?.output_json_schema}
      show_name_field={false}
      model_dropdown_settings={{
        requires_structured_output: !!task?.output_json_schema,
        requires_data_gen: true,
        suggested_mode: "data_gen",
      }}
    />
  </Dialog>
{:else}
  <Dialog
    bind:this={combined_config_dialog}
    title="Generation Options"
    sub_subtitle="Configure the run options used to generate example inputs and outputs."
    width="wide"
    action_buttons={[{ label: "Done", isPrimary: true }]}
  >
    <div class="flex flex-col gap-6">
      <div>
        <div class="font-medium">Input Generation</div>
        <div class="text-sm text-gray-500 mb-3">
          Used to generate example inputs.
        </div>
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
      <div class="border-t"></div>
      <div>
        <div class="font-medium">Output Generation</div>
        <div class="text-sm text-gray-500 mb-3">
          Used to generate example outputs.
        </div>
        <RunConfigComponent
          bind:this={output_run_config_component}
          bind:model_name={output_model_name}
          model={recommended_data_gen_model}
          prompt_method={output_default_prompt_method}
          tools={output_default_tools}
          skills={output_default_skills}
          {project_id}
          current_task={task}
          requires_structured_output={!!task?.output_json_schema}
          show_name_field={false}
          model_dropdown_settings={{
            requires_structured_output: !!task?.output_json_schema,
            requires_data_gen: true,
            suggested_mode: "data_gen",
          }}
        />
      </div>
    </div>
  </Dialog>
{/if}
