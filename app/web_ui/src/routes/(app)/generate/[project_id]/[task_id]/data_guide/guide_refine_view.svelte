<script lang="ts">
  // Shown when the user already has a saved data guide and revisits this page.
  // Skips the build-from-examples setup form and goes straight to "preview the
  // existing guide → refine via the metaprompter loop".
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import Output from "$lib/ui/output.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type {
    Task,
    KilnAgentRunConfigProperties,
    RunConfigProperties,
  } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import RunOptionsTiles from "./run_options_tiles.svelte"

  export let project_id: string
  export let guide: string
  export let task: Task | null = null

  let page_error: KilnError | null = null
  let page_submitting: boolean = false
  let run_options_tiles: RunOptionsTiles | null = null

  const dispatch = createEventDispatcher<{
    generate_preview: {
      guide: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }
    restart_setup: void
  }>()

  function handle_refine() {
    page_error = null
    try {
      if (!guide.trim()) {
        page_error = new KilnError(
          "No saved data guide found. Set one up first.",
          null,
        )
        return
      }
      const input_run_config: RunConfigProperties | null =
        run_options_tiles?.get_input_run_config() ?? null
      const output_run_config: RunConfigProperties | null =
        run_options_tiles?.get_output_run_config() ?? null
      if (!input_run_config || !output_run_config) {
        page_error = new KilnError(
          "Please select a model for input and output generation.",
          null,
        )
        return
      }
      if (
        !isKilnAgentRunConfig(input_run_config) ||
        !isKilnAgentRunConfig(output_run_config)
      ) {
        page_error = new KilnError(
          "Task Data Guide requires a kiln_agent run config.",
          null,
        )
        return
      }
      dispatch("generate_preview", {
        guide,
        input_run_config,
        output_run_config,
      })
    } finally {
      page_submitting = false
    }
  }
</script>

<FormContainer
  submit_label="Refine"
  on:submit={handle_refine}
  bind:error={page_error}
  bind:submitting={page_submitting}
  compact_button={true}
>
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div>
        <div class="font-medium">Saved Data Guide</div>
        <div class="text-sm text-gray-500">
          The guide currently saved for this task. Refine generates new examples
          and lets you mark each as Realistic or Needs Work to iterate.
        </div>
      </div>
      <button
        type="button"
        class="btn btn-sm btn-outline"
        on:click={() => dispatch("restart_setup")}
      >
        Start Over
      </button>
    </div>
    <Output raw_output={guide} show_border={true} background_color="white" />
  </div>

  <RunOptionsTiles bind:this={run_options_tiles} {project_id} {task} />
</FormContainer>
