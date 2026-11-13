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
  import { reset_schema_to_form_schema } from "$lib/utils/openenv_reset_schema"
  import {
    RESET_ARGUMENTS_DESCRIPTION,
    RESET_ARGUMENTS_SCHEMA_DESCRIPTION,
    blank_draft,
    clone_draft,
    draft_from,
    load_openenv_server_reset_schema,
    presets_with_draft,
    reset_arguments_for_form,
    reset_arguments_from_form,
    type PresetDraft,
  } from "./openenv_server_detail"

  export let project_id: string
  export let openenv_server_id: string
  export let presets: NamedResetKwargs[]
  /** Saves the whole list. Throws when the server refuses it. */
  export let save: (presets: NamedResetKwargs[]) => Promise<void>

  let dialog: Dialog
  // The form is only mounted while the dialog is open, so the code editor
  // starts from each draft and Cmd+Enter can't submit a closed dialog.
  let open = false
  let editing_index: number | null = null
  let draft: PresetDraft = blank_draft()
  let error: KilnError | null = null
  let submitting = false

  // Null until the server's reset schema loads, and when it has none the form
  // can show. The JSON editor shows until then, so a slow server never blocks.
  let form_schema: JsonSchemaProperty | null = null
  let raw_json = true
  let opened_text = ""
  let schema_request = 0
  let reset_form: RunInputForm

  function show(index: number | null, next_draft: PresetDraft) {
    editing_index = index
    draft = next_draft
    opened_text = next_draft.reset_arguments
    error = null
    form_schema = null
    raw_json = true
    open = true
    dialog.show()
    load_form_schema()
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

  async function load_form_schema() {
    const request = ++schema_request
    let schema: JsonSchemaProperty | null = null
    try {
      schema = reset_schema_to_form_schema(
        await load_openenv_server_reset_schema(project_id, openenv_server_id),
      )
    } catch {
      // The detail page already shows when the server can't be reached.
      schema = null
    }
    if (request !== schema_request || !open || !schema) {
      return
    }
    form_schema = schema
    // A schema that arrives after the user has typed doesn't move them.
    if (draft.reset_arguments !== opened_text) {
      return
    }
    const result = reset_arguments_for_form(draft.reset_arguments, schema)
    if ("form_value" in result) {
      await show_form(result.form_value)
    }
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
  on:close={() => (open = false)}
>
  {#if open}
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
          subtitle={form_schema
            ? RESET_ARGUMENTS_SCHEMA_DESCRIPTION
            : RESET_ARGUMENTS_DESCRIPTION}
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
