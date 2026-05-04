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
  export let examples_md: string
  export let rules_md: string
  export let task: Task | null = null
  // The full DataGuide model so we can surface metadata (created_at /
  // created_by) in the right column.
  export let data_guide: DataGuide | null = null

  // Exported so the parent can surface async errors (e.g. a failed preview
  // API call) inline above the Refine button. Cleared by handle_refine on
  // each new attempt.
  export let page_error: KilnError | null = null
  let page_submitting: boolean = false

  // Bound from the parent's PUT handler so the "Save Without Verifying" link
  // in the edit dialog can render its own pending state and inline failure
  // message. Without these the dialog stays open with no feedback if the save
  // PUT fails — only the parent page sees the error.
  export let save_error: KilnError | null = null
  export let save_submitting: boolean = false
  let run_options_tiles: RunOptionsTiles | null = null
  // Bound so the right-column Verify button (rendered outside FormContainer's
  // own submit slot) can drive validate_and_submit. Without this our custom
  // submit button just triggers the form's native submit handler, which
  // FormContainer preventDefaults — so nothing dispatches.
  let form_container: FormContainer

  const dispatch = createEventDispatcher<{
    generate_preview: {
      examples_md: string
      rules_md: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }
    save: { examples_md: string; rules_md: string }
  }>()

  // --- Edit-and-go dialog ---
  // Lets the user manually tweak the data guide (both halves) and jump
  // straight into the preview/review flow with the edited version (no need
  // to rebuild from scratch via the setup form). The dialog's submit button
  // reuses the same generate_preview event so the rest of the flow is
  // unchanged.
  let edit_dialog: Dialog
  let editing_examples_md: string = examples_md
  let editing_rules_md: string = rules_md
  let edit_submit_error: KilnError | null = null
  // Sync the editing buffers once the parent loads the saved guide. Without
  // this, warn_before_unload on the dialog's FormContainer would compare an
  // empty buffer to a populated saved value and fire on every navigation.
  let editing_initialized: boolean = false
  $: if (!editing_initialized && (examples_md || rules_md)) {
    editing_examples_md = examples_md
    editing_rules_md = rules_md
    editing_initialized = true
  }

  $: editing_has_changes =
    editing_examples_md !== examples_md || editing_rules_md !== rules_md
  $: editing_is_empty = !editing_examples_md.trim() && !editing_rules_md.trim()

  // Exported so the parent can wire the Edit action into the AppPage header
  // (we keep the dialog itself inside this component since it shares all the
  // refine-flow state).
  export function open_edit_dialog() {
    editing_examples_md = examples_md
    editing_rules_md = rules_md
    edit_submit_error = null
    edit_dialog?.show()
  }

  // Pulls run options from the parent's RunOptionsTiles + validates them. Used
  // by both the main Verify button and the edit dialog's submit button so
  // they share validation rules.
  function build_preview_dispatch(
    examples_value: string,
    rules_value: string,
  ):
    | {
        examples_md: string
        rules_md: string
        input_run_config: KilnAgentRunConfigProperties
        output_run_config: KilnAgentRunConfigProperties
      }
    | { error: KilnError } {
    if (!examples_value.trim() && !rules_value.trim()) {
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
      examples_md: examples_value,
      rules_md: rules_value,
      input_run_config,
      output_run_config,
    }
  }

  function handle_refine() {
    page_error = null
    try {
      const result = build_preview_dispatch(examples_md, rules_md)
      if ("error" in result) {
        page_error = result.error
        return
      }
      dispatch("generate_preview", result)
    } finally {
      page_submitting = false
    }
  }

  // Flipped true the moment the user clicks Verify Changes — the parent
  // immediately goto's /refine, which trips the FormContainer's
  // beforeNavigate guard. Without this flag the user gets prompted to
  // confirm leaving even though they explicitly chose to leave; the verify
  // flow at /refine carries its own warn for unsaved work.
  let verifying = false

  function handle_edit_submit() {
    edit_submit_error = null
    const result = build_preview_dispatch(editing_examples_md, editing_rules_md)
    if ("error" in result) {
      edit_submit_error = result.error
      return
    }
    verifying = true
    edit_dialog?.close()
    dispatch("generate_preview", result)
  }

  // Set true when we dispatch a save and need to react to the parent's
  // resulting save_submitting transition. Prevents the close-on-success
  // reactive block from firing for unrelated save_submitting changes.
  let awaiting_save = false

  // Watch save_submitting flip back to false after we dispatched a save.
  // Success → close the dialog. Failure → leave it open so the user sees
  // save_error inline and can retry.
  $: if (awaiting_save && !save_submitting) {
    awaiting_save = false
    if (!save_error) edit_dialog?.close()
  }

  function handle_save_without_verifying() {
    edit_submit_error = null
    save_error = null
    if (editing_is_empty) {
      edit_submit_error = new KilnError(
        "Data guide cannot be empty. Add some content first.",
        null,
      )
      return
    }
    awaiting_save = true
    dispatch("save", {
      examples_md: editing_examples_md,
      rules_md: editing_rules_md,
    })
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
    <div class="grow max-w-[900px] flex flex-col gap-6">
      <div class="flex flex-col gap-2">
        <h2 class="text-lg font-medium">Reference Examples</h2>
        {#if examples_md.trim()}
          <Output raw_output={examples_md} />
        {:else}
          <div
            class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-400"
          >
            No reference examples
          </div>
        {/if}
      </div>
      {#if rules_md.trim()}
        <div class="flex flex-col gap-2">
          <h2 class="text-lg font-medium">Guidelines &amp; Rules</h2>
          <Output raw_output={rules_md} />
        </div>
      {/if}
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
     the Refine button uses, but with the manually edited guide. Run options
     come from the parent's RunOptionsTiles so the user doesn't have to
     re-pick models. -->
<Dialog bind:this={edit_dialog} title="Edit Data Guide" width="wide">
  <FormContainer
    submit_label="Verify Changes"
    submit_disabled={editing_is_empty}
    submit_visible={editing_has_changes}
    on:submit={handle_edit_submit}
    bind:error={edit_submit_error}
    compact_button={true}
    warn_before_unload={editing_has_changes && !verifying}
  >
    <div class="flex flex-col gap-6">
      <div>
        <div class="flex flex-row items-center pb-[4px]">
          <span class="text-sm font-medium">Reference Examples</span>
          <span class="grow"></span>
          {#if editing_examples_md !== examples_md}
            <button
              type="button"
              class="link text-xs text-gray-500 hover:text-gray-700"
              on:click|stopPropagation={() =>
                (editing_examples_md = examples_md)}
            >
              Reset
            </button>
          {/if}
        </div>
        <FormElement
          label="Reference Examples"
          hide_label={true}
          id="edit_examples_text"
          inputType="textarea"
          height="xl"
          bind:value={editing_examples_md}
          optional={true}
          hide_optional_badge={true}
        />
      </div>
      <div>
        <div class="flex flex-row items-center pb-[4px]">
          <span class="text-sm font-medium">Guidelines &amp; Rules</span>
          <span class="grow"></span>
          <span class="pl-1 text-xs text-gray-500 flex-none">Optional</span>
          {#if editing_rules_md !== rules_md}
            <button
              type="button"
              class="link ml-4 text-xs text-gray-500 hover:text-gray-700"
              on:click|stopPropagation={() => (editing_rules_md = rules_md)}
            >
              Reset
            </button>
          {/if}
        </div>
        <FormElement
          label="Guidelines & Rules"
          hide_label={true}
          id="edit_rules_text"
          inputType="textarea"
          height="xl"
          bind:value={editing_rules_md}
          optional={true}
          hide_optional_badge={true}
        />
      </div>
    </div>
  </FormContainer>
  {#if editing_has_changes}
    <div class="flex flex-col gap-2 mt-4 items-end">
      <div class="flex flex-row gap-1 items-center">
        <span class="text-sm text-gray-500">or</span>
        <button
          type="button"
          class="link underline text-sm text-gray-500"
          disabled={save_submitting || editing_is_empty}
          on:click={handle_save_without_verifying}
        >
          {#if save_submitting}
            <span class="loading loading-spinner loading-xs"></span> Saving…
          {:else}
            Save Without Verifying
          {/if}
        </button>
      </div>
      {#if save_error}
        <div class="text-sm text-error">
          {save_error.getMessage()}
        </div>
      {/if}
    </div>
  {/if}
</Dialog>
