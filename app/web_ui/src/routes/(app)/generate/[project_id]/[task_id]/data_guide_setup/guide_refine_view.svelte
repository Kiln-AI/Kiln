<script lang="ts">
  // Shown when the user already has a saved input data guide and revisits
  // this page. Skips the build-from-examples setup form and goes straight to
  // "preview the existing guide → refine via the metaprompter loop".
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Output from "$lib/ui/output.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type {
    KilnAgentRunConfigProperties,
    RunConfigProperties,
    DataGuide,
  } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import RunOptionsTiles from "./run_options_tiles.svelte"
  import GenerationSettingsTrigger from "./generation_settings_trigger.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import OptionList from "$lib/ui/option_list.svelte"
  import type { OptionListItem } from "$lib/ui/option_list_types"

  export let project_id: string
  export let guide: string
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
  // Friendly names of the selected generation model + provider, for the
  // settings widget shown above "Verify Changes" in the edit dialog.
  let generation_model_name = ""
  let generation_provider = ""
  // Bound so the right-column Verify button (rendered outside FormContainer's
  // own submit slot) can drive validate_and_submit. Without this our custom
  // submit button just triggers the form's native submit handler, which
  // FormContainer preventDefaults — so nothing dispatches.
  let form_container: FormContainer

  const dispatch = createEventDispatcher<{
    generate_preview: {
      guide: string
      input_run_config: KilnAgentRunConfigProperties
    }
    save: { guide: string }
  }>()

  // --- Edit-and-go dialog ---
  // Lets the user manually tweak the data guide and jump straight into the
  // preview/review flow with the edited version (no need to rebuild from
  // scratch via the setup form). The dialog's submit button reuses the same
  // generate_preview event so the rest of the flow is unchanged.
  let edit_dialog: Dialog
  let editing_guide: string = guide
  let edit_submit_error: KilnError | null = null
  // Sync the editing buffer once the parent loads the saved guide. Without
  // this, warn_before_unload on the dialog's FormContainer would compare an
  // empty buffer to a populated saved value and fire on every navigation.
  let editing_initialized: boolean = false
  $: if (!editing_initialized && guide) {
    editing_guide = guide
    editing_initialized = true
  }

  $: editing_has_changes = editing_guide !== guide
  $: editing_is_empty = !editing_guide.trim()
  // Verify Changes (and the settings widget above it) are always shown but
  // disabled until there's a non-empty edit to verify.
  $: verify_disabled = !editing_has_changes || editing_is_empty

  // Exported so the parent can wire the Edit action into the AppPage header
  // (we keep the dialog itself inside this component since it shares all the
  // refine-flow state).
  export function open_edit_dialog() {
    editing_guide = guide
    edit_submit_error = null
    // Reset verifying — the happy path destroys this component on the
    // post-Verify goto, but if a prior Verify attempt didn't navigate
    // (parent's goto failed, beforeNavigate cancelled, etc.) the flag
    // could still be true and would silently disable warn_before_unload.
    verifying = false
    edit_dialog?.show()
  }

  // --- Edit chooser dialog ---
  // The header "Edit" action opens this first, letting the user pick between
  // editing the guide text by hand or reviewing generated examples (and
  // refining). Replaces the old standalone "Refine Data Guide" button.
  let edit_chooser_dialog: Dialog

  const edit_options: OptionListItem[] = [
    {
      id: "manual",
      name: "Edit Manually",
      description:
        "Edit the guide text directly, then verify your changes or save without verifying.",
    },
    {
      id: "review",
      name: "Review & Refine",
      description:
        "Generate example inputs from your guide to check quality, and refine it if any need work.",
    },
  ]

  export function open_edit_chooser() {
    edit_chooser_dialog?.show()
  }

  function handle_edit_choice(id: string) {
    if (id === "manual") {
      // Open the edit dialog on top of the chooser so it reads as a distinct
      // new dialog rather than the chooser's contents swapping in place. The
      // chooser is closed when the edit dialog closes (see below).
      open_edit_dialog()
    } else if (id === "review") {
      edit_chooser_dialog?.close()
      // Open the generation settings modal with a "Continue" action that then
      // runs the review/refine flow with the chosen model.
      run_options_tiles?.open_combined_dialog({
        label: "Continue",
        action: handle_review_continue,
      })
    }
  }

  // "Continue" from the generation settings modal on the review path: kick off
  // the same validated preview dispatch the old Refine button used, then let
  // the dialog close.
  function handle_review_continue(): boolean {
    handle_refine()
    return true
  }

  // On edit-dialog close (X, Escape, or after submit): discard any unsaved
  // edits — without this a stale buffer keeps editing_has_changes true and
  // trips warn_before_unload on a later navigation instead of at close time —
  // and close the chooser underneath so we land back on the page, not the
  // chooser.
  function handle_edit_dialog_close() {
    editing_guide = guide
    edit_submit_error = null
    edit_chooser_dialog?.close()
  }

  // Pulls run options from the parent's RunOptionsTiles + validates them. Used
  // by both the main Verify button and the edit dialog's submit button so
  // they share validation rules.
  function build_preview_dispatch(guide_value: string):
    | {
        guide: string
        input_run_config: KilnAgentRunConfigProperties
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
    if (!input_run_config) {
      return {
        error: new KilnError(
          "Please select a model for input generation.",
          null,
        ),
      }
    }
    if (!isKilnAgentRunConfig(input_run_config)) {
      return {
        error: new KilnError(
          "Data Guide requires a kiln_agent run config.",
          null,
        ),
      }
    }
    return {
      guide: guide_value,
      input_run_config,
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

  // Flipped true the moment the user clicks Verify Changes — the parent
  // immediately goto's /refine, which trips the FormContainer's
  // beforeNavigate guard. Without this flag the user gets prompted to
  // confirm leaving even though they explicitly chose to leave; the verify
  // flow at /refine carries its own warn for unsaved work.
  let verifying = false

  function handle_edit_submit() {
    edit_submit_error = null
    const result = build_preview_dispatch(editing_guide)
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
    dispatch("save", { guide: editing_guide })
  }

  $: data_guide_properties = build_data_guide_properties(data_guide)

  const source_labels: Record<NonNullable<DataGuide["source"]>, string> = {
    manual: "Manual",
    kiln_pro: "Kiln Pro",
  }

  function build_data_guide_properties(g: DataGuide | null): UiProperty[] {
    const props: UiProperty[] = []
    if (g?.id) {
      props.push({ name: "ID", value: g.id })
    }
    if (g?.source) {
      props.push({
        name: "Source",
        value: source_labels[g.source] ?? g.source,
      })
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

      <!-- Renders nothing in `link` mode; supplies the run config + the combined
           settings dialog used by the edit dialog's settings widget and the
           Review & Refine flow. -->
      <RunOptionsTiles
        bind:this={run_options_tiles}
        bind:selected_model_name_display={generation_model_name}
        bind:selected_provider_display={generation_provider}
        {project_id}
      />
    </aside>
  </div>
</FormContainer>

<!-- Edit chooser: the header "Edit" action opens this to pick manual text
     editing vs. reviewing generated examples (and refining). -->
<Dialog
  bind:this={edit_chooser_dialog}
  title="Edit Data Guide"
  sub_subtitle="Choose how you'd like to update your guide."
  width="wide"
>
  <OptionList options={edit_options} select_option={handle_edit_choice} />
</Dialog>

<!-- Edit-and-go dialog. Submitting jumps straight into the same preview flow
     the old Refine button used, but with the manually edited guide. Run options
     come from the parent's RunOptionsTiles so the user doesn't have to
     re-pick models. -->
<Dialog
  bind:this={edit_dialog}
  title="Edit Data Guide"
  width="wide"
  on:close={handle_edit_dialog_close}
>
  <FormContainer
    submit_label="Verify Changes"
    submit_disabled={verify_disabled}
    on:submit={handle_edit_submit}
    bind:error={edit_submit_error}
    compact_button={true}
    warn_before_unload={editing_has_changes && !verifying}
  >
    <div>
      <div class="flex flex-row items-center pb-[4px]">
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
      <FormElement
        label="Data Guide"
        hide_label={true}
        id="edit_guide_text"
        inputType="textarea"
        height="xl"
        bind:value={editing_guide}
      />
    </div>
    {#if editing_has_changes}
      <GenerationSettingsTrigger
        model_name={generation_model_name}
        provider={generation_provider}
        open={() => run_options_tiles?.open_combined_dialog()}
      />
    {/if}
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
