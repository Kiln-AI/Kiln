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
    DataGuide,
  } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import RunOptionsTiles from "./run_options_tiles.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"

  export let project_id: string
  export let guide: string
  export let task: Task | null = null
  // The full DataGuide model so we can surface metadata (created_at /
  // created_by) in the right column. Null for legacy tasks that only have a
  // raw guide string.
  export let data_guide: DataGuide | null = null

  // Exported so the parent can surface async errors (e.g. a failed preview
  // API call) inline above the Refine button. Cleared by handle_refine on
  // each new attempt.
  export let page_error: KilnError | null = null
  let page_submitting: boolean = false
  let run_options_tiles: RunOptionsTiles | null = null
  // Bound so the right-column Verify button (rendered outside FormContainer's
  // own submit slot) can drive validate_and_submit. Without this our custom
  // submit button just triggers the form's native submit handler, which
  // FormContainer preventDefaults — so nothing dispatches.
  let form_container: FormContainer

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
  let editing_guide: string = guide
  let edit_submit_error: KilnError | null = null
  // Sync editing_guide once `guide` is loaded by the parent so warn_before_unload
  // on the edit dialog's FormContainer doesn't fire on a fresh page visit
  // (where the user hasn't even opened the dialog).
  let editing_guide_initialized: boolean = false
  $: if (!editing_guide_initialized && guide) {
    editing_guide = guide
    editing_guide_initialized = true
  }

  // Exported so the parent can wire the Edit action into the AppPage header
  // (we keep the dialog itself inside this component since it shares all the
  // refine-flow state).
  export function open_edit_dialog() {
    editing_guide = guide
    edit_submit_error = null
    edit_dialog?.show()
  }

  // Pulls run options from the parent's RunOptionsTiles + validates them. Used
  // by both the main Verify button and the edit dialog's "Verify Data Guide"
  // button so they share validation rules.
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

  function handle_save_without_verifying() {
    edit_submit_error = null
    if (!editing_guide.trim()) {
      edit_submit_error = new KilnError(
        "Data guide cannot be empty. Add some content first.",
        null,
      )
      return
    }
    dispatch("save", { guide: editing_guide })
  }

  $: data_guide_properties = build_data_guide_properties(data_guide)

  function build_data_guide_properties(g: DataGuide | null): UiProperty[] {
    const props: UiProperty[] = []
    if (g?.id) {
      props.push({ name: "ID", value: g.id })
    }
    if (g?.created_at) {
      props.push({ name: "Created At", value: formatDate(g.created_at) })
    }
    if (g?.created_by) {
      props.push({ name: "Created By", value: g.created_by })
    }
    return props
  }
</script>

<FormContainer
  bind:this={form_container}
  on:submit={handle_refine}
  bind:error={page_error}
  bind:submitting={page_submitting}
  submit_visible={false}
>
  <div class="grid grid-cols-1 lg:grid-cols-[1fr,auto] gap-12">
    <div class="grow max-w-[900px] flex flex-col gap-2">
      <Output raw_output={guide} />
    </div>

    <aside class="flex flex-col gap-4 self-start lg:w-64">
      {#if data_guide_properties.length > 0}
        <PropertyList title="Properties" properties={data_guide_properties} />
      {/if}

      <button
        type="button"
        class="btn btn-sm btn-outline w-full mt-4"
        disabled={page_submitting}
        on:click={() => form_container?.validate_and_submit()}
      >
        {#if page_submitting}
          <span class="loading loading-spinner loading-xs"></span>
        {:else}
          Test Data Guide
        {/if}
      </button>

      <div class="flex justify-end -mt-2">
        <button
          type="button"
          class="link text-sm text-gray-500 hover:text-gray-700"
          on:click={() => run_options_tiles?.open_combined_dialog()}
        >
          Generation options
        </button>
      </div>
      <RunOptionsTiles
        bind:this={run_options_tiles}
        mode="link"
        {project_id}
        {task}
      />
    </aside>
  </div>
</FormContainer>

<!-- Edit-and-go dialog. Submitting jumps straight into the same preview flow
     the Refine button uses, but with the manually edited guide string. The
     run options come from the parent's RunOptionsTiles so the user doesn't
     have to re-pick models. -->
<Dialog bind:this={edit_dialog} title="Edit Data Guide" width="wide">
  <FormContainer
    submit_label="Verify Changes"
    submit_disabled={!editing_guide.trim()}
    submit_visible={editing_guide !== guide}
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
            {#if editing_guide !== guide}
              <button
                type="button"
                class="link ml-4 text-xs text-gray-500 hover:text-gray-700"
                on:click|stopPropagation={() => (editing_guide = guide)}
              >
                Reset
              </button>
            {/if}
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
  {#if editing_guide !== guide}
    <div class="flex flex-row gap-1 mt-4 justify-end">
      <span class="text-sm text-gray-500">or</span>
      <button
        class="link underline text-sm text-gray-500"
        on:click={handle_save_without_verifying}
      >
        Save Without Verifying
      </button>
    </div>
  {/if}
</Dialog>
