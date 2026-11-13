<script lang="ts">
  import { tick } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"
  import RunInputForm from "../../../../run/run_input_form.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { NamedResetKwargs } from "$lib/types"
  import type { JsonSchemaProperty } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    RESET_ARGUMENTS_DESCRIPTION,
    RESET_ARGUMENTS_SCHEMA_DESCRIPTION,
    blank_draft,
    clone_draft,
    draft_from,
    presets_with_draft,
    reset_arguments_for_form,
    reset_arguments_from_form,
    type PresetDraft,
  } from "./openenv_server_detail"

  export let presets: NamedResetKwargs[]
  /**
   * The form for the server's reset arguments, loaded by the page. Null when
   * the server has none the form can show, or can't be reached: the dialog
   * then edits Raw JSON only.
   */
  export let form_schema: JsonSchemaProperty | null
  export let form_schema_loading: boolean
  /** Saves the whole list. Throws when the server refuses it. */
  export let save: (presets: NamedResetKwargs[]) => Promise<void>

  let dialog: Dialog
  // The form is only mounted while the dialog is open, so the code editor
  // starts from each draft and Cmd+Enter can't submit a closed dialog.
  let open = false
  // False until the dialog knows whether it starts on the form or Raw JSON, so
  // the whole body renders at once rather than growing as the schema arrives.
  let ready = false
  let editing_index: number | null = null
  let draft: PresetDraft = blank_draft()
  let error: KilnError | null = null
  let submitting = false

  let raw_json = true
  let reset_form: RunInputForm

  function show(index: number | null, next_draft: PresetDraft) {
    editing_index = index
    draft = next_draft
    error = null
    raw_json = true
    ready = false
    open = true
    dialog.show()
  }

  $: if (open && !ready && !form_schema_loading) {
    start_body()
  }

  async function start_body() {
    ready = true
    if (!form_schema) {
      return
    }
    const result = reset_arguments_for_form(draft.reset_arguments, form_schema)
    if ("form_value" in result) {
      await show_form(result.form_value)
    }
  }

  export function show_add() {
    show(null, blank_draft())
  }

  export function show_edit(index: number) {
    show(index, draft_from(presets[index]))
  }

  export function show_clone(index: number) {
    show(null, clone_draft(presets[index]))
  }

  async function show_form(form_value: unknown) {
    raw_json = false
    await tick()
    await reset_form?.set_structured_input_data(form_value)
  }

  /** The form's value, or null after showing why it can't be read. */
  function read_form(): unknown | null {
    try {
      return reset_form.get_structured_input_data()
    } catch (e) {
      error = e instanceof Error ? new KilnError(e.message) : createKilnError(e)
      return null
    }
  }

  async function toggle_raw_json() {
    error = null
    if (!form_schema) {
      return
    }
    if (raw_json) {
      const result = reset_arguments_for_form(
        draft.reset_arguments,
        form_schema,
      )
      if ("error" in result) {
        error = new KilnError(result.error)
        return
      }
      await show_form(result.form_value)
      return
    }
    const form_value = read_form()
    if (form_value === null) {
      return
    }
    draft = { ...draft, reset_arguments: reset_arguments_from_form(form_value) }
    raw_json = true
  }

  async function submit() {
    error = null
    if (!raw_json) {
      const form_value = read_form()
      if (form_value === null) {
        submitting = false
        return
      }
      draft = {
        ...draft,
        reset_arguments: reset_arguments_from_form(form_value),
      }
    }
    const result = presets_with_draft(presets, editing_index, draft)
    if (result.error !== null) {
      error = new KilnError(result.error)
      submitting = false
      return
    }
    try {
      await save(result.presets)
      dialog.close()
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title={editing_index === null
    ? "Add Environment Preset"
    : "Edit Environment Preset"}
  width="wide"
  on:close={() => (open = false)}
>
  {#if open && !ready}
    <div class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>
  {:else if open}
    <FormContainer
      submit_label="Save"
      on:submit={submit}
      bind:submitting
      {error}
    >
      <FormElement
        label="Name"
        id="environment_preset_name"
        description="Shown in the Environment Preset dropdown on the run page."
        info_description={'For example, "Small Startup" or "Large Company, Admin User".'}
        bind:value={draft.name}
        max_length={120}
        placeholder="Name"
      />
      <FormElement
        label="Description"
        inputType="textarea"
        id="environment_preset_description"
        description="Shown under the name in the Environment Preset dropdown."
        optional={true}
        bind:value={draft.description}
      />
      <div class="flex flex-col gap-4">
        <!-- A section over its own fields, so it takes the section header a
             level above them. Kiln has no inline on/off switch, so the Raw
             JSON toggle is a link on the header's row, named for the view it
             opens. -->
        <SettingsHeader
          title="Reset Arguments"
          subtitle={raw_json
            ? RESET_ARGUMENTS_DESCRIPTION
            : RESET_ARGUMENTS_SCHEMA_DESCRIPTION}
        >
          <svelte:fragment slot="actions">
            {#if form_schema}
              <button
                type="button"
                class="link text-xs text-gray-500 hover:text-gray-700"
                on:click|stopPropagation={toggle_raw_json}
                >{raw_json ? "Form" : "Raw JSON"}</button
              >
            {/if}
          </svelte:fragment>
        </SettingsHeader>
        {#if raw_json}
          <CodeEditor
            language="json"
            min_height="160px"
            bind:value={draft.reset_arguments}
          />
        {:else if form_schema}
          <RunInputForm
            bind:this={reset_form}
            input_schema={JSON.stringify(form_schema)}
            hide_label
          />
        {/if}
      </div>
    </FormContainer>
  {/if}
</Dialog>
