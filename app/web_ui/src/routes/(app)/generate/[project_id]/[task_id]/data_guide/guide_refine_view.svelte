<script lang="ts">
  // Shown when the user already has a saved data guide and revisits this page.
  // Skips the build-from-examples setup form and goes straight to "preview the
  // existing guide → refine via the metaprompter loop".
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Output from "$lib/ui/output.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
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

  // Exported so the parent can surface async errors (e.g. a failed preview
  // API call) inline above the Refine button. Cleared by handle_refine on
  // each new attempt.
  export let page_error: KilnError | null = null
  let page_submitting: boolean = false
  let run_options_tiles: RunOptionsTiles | null = null

  const dispatch = createEventDispatcher<{
    generate_preview: {
      guide: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }
    save: { guide: string }
  }>()

  // --- Edit-and-go dialog ---
  // Lets the user manually tweak the saved guide and jump straight into the
  // preview/review flow with the edited version (no need to rebuild from
  // scratch via the setup form). The dialog's submit button reuses the same
  // generate_preview event so the rest of the flow is unchanged.
  let edit_dialog: Dialog
  let editing_guide: string = ""
  let edit_submit_error: KilnError | null = null

  function open_edit_dialog() {
    editing_guide = guide
    edit_submit_error = null
    edit_dialog?.show()
  }

  // Pulls run options from the parent's RunOptionsTiles + validates them. Used
  // by both the main Refine button and the edit dialog's
  // "Generate & Review Examples" button so they share validation rules.
  function build_preview_dispatch(guide_value: string):
    | {
        guide: string
        input_run_config: KilnAgentRunConfigProperties
        output_run_config: KilnAgentRunConfigProperties
      }
    | { error: KilnError } {
    if (!guide_value.trim()) {
      return {
        error: new KilnError(
          "Data guide cannot be empty. Add some content first.",
          null,
        ),
      }
    }
    const input_run_config: RunConfigProperties | null =
      run_options_tiles?.get_input_run_config() ?? null
    const output_run_config: RunConfigProperties | null =
      run_options_tiles?.get_output_run_config() ?? null
    if (!input_run_config || !output_run_config) {
      return {
        error: new KilnError(
          "Please select a model for input and output generation.",
          null,
        ),
      }
    }
    if (
      !isKilnAgentRunConfig(input_run_config) ||
      !isKilnAgentRunConfig(output_run_config)
    ) {
      return {
        error: new KilnError(
          "Task Data Guide requires a kiln_agent run config.",
          null,
        ),
      }
    }
    return {
      guide: guide_value,
      input_run_config,
      output_run_config,
    }
  }

  function handle_refine() {
    page_error = null
    try {
      const result = build_preview_dispatch(guide)
      if ("error" in result) {
        page_error = result.error
        return
      }
      dispatch("generate_preview", result)
    } finally {
      page_submitting = false
    }
  }

  function handle_edit_submit() {
    edit_submit_error = null
    const result = build_preview_dispatch(editing_guide)
    if ("error" in result) {
      edit_submit_error = result.error
      return
    }
    edit_dialog?.close()
    dispatch("generate_preview", result)
  }

  function handle_save_without_reviewing() {
    edit_submit_error = null
    if (!editing_guide.trim()) {
      edit_submit_error = new KilnError(
        "Data guide cannot be empty. Add some content first.",
        null,
      )
      return
    }
    edit_dialog?.close()
    dispatch("save", { guide: editing_guide })
  }
</script>

<FormContainer
  submit_label="Generate & Review Examples"
  on:submit={handle_refine}
  bind:error={page_error}
  bind:submitting={page_submitting}
  compact_button={true}
  submit_row_class="bg-base-200 rounded-lg p-3"
>
  <!-- Run option tiles live in the submit_left slot so they share a styled
       row with the submit button. -->
  <svelte:fragment slot="submit_left">
    <RunOptionsTiles bind:this={run_options_tiles} {project_id} {task} />
  </svelte:fragment>

  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div>
        <div class="font-medium">Saved Data Guide</div>
        <div class="text-sm text-gray-500">
          The guide currently saved for this task passed in during synthetic
          data generation. Generate examples to review and rate to iterate on
          the guide.
        </div>
      </div>
      <button
        type="button"
        class="btn btn-sm btn-outline"
        on:click={open_edit_dialog}
      >
        Edit
      </button>
    </div>
    <Output raw_output={guide} />
  </div>
</FormContainer>

<!-- Edit-and-go dialog. Submitting jumps straight into the same preview flow
     the Refine button uses, but with the manually edited guide string. The
     run options come from the parent's RunOptionsTiles so the user doesn't
     have to re-pick models. -->
<Dialog
  bind:this={edit_dialog}
  title="Edit Data Guide"
  sub_subtitle="Manually update the saved guide and jump straight into reviewing fresh examples — no need to rebuild from scratch."
  width="wide"
>
  <FormContainer
    submit_label="Generate & Review Examples"
    submit_disabled={!editing_guide.trim()}
    on:submit={handle_edit_submit}
    bind:error={edit_submit_error}
    compact_button={true}
    warn_before_unload={editing_guide !== guide}
  >
    <div>
      <div class="flex flex-row items-center gap-2 pb-[4px]">
        <div class="text-sm font-medium text-left flex flex-col gap-1 w-full">
          <div class="flex flex-row items-center">
            <span class="grow"></span>
            <button
              type="button"
              class="link ml-4 text-xs text-gray-500 hover:text-gray-700 disabled:text-gray-300 disabled:no-underline"
              disabled={editing_guide === guide}
              on:click|stopPropagation={() => (editing_guide = guide)}
            >
              Reset
            </button>
          </div>
        </div>
      </div>
      <FormElement
        label="Data Guide"
        hide_label={true}
        id="edit_guide_text"
        inputType="textarea"
        height="xl"
        bind:value={editing_guide}
      />
    </div>
  </FormContainer>
  <div class="flex flex-row gap-1 mt-4 justify-end">
    <span class="text-sm text-gray-500">or</span>
    <button
      class="link underline text-sm text-gray-500"
      on:click={handle_save_without_reviewing}
    >
      Save Without Reviewing
    </button>
  </div>
</Dialog>
