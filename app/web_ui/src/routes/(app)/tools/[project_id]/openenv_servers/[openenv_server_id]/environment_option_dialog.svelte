<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { NamedResetKwargs } from "$lib/types"
  import {
    blank_draft,
    clone_draft,
    draft_from,
    options_with_draft,
    type OptionDraft,
  } from "./openenv_server_detail"

  export let options: NamedResetKwargs[]
  /** Saves the whole list. Throws when the server refuses it. */
  export let save: (options: NamedResetKwargs[]) => Promise<void>

  let dialog: Dialog
  // The form is only mounted while the dialog is open, so the code editor
  // starts from each draft and Cmd+Enter can't submit a closed dialog.
  let open = false
  let editing_index: number | null = null
  let draft: OptionDraft = blank_draft()
  let error: KilnError | null = null
  let submitting = false

  function show(index: number | null, next_draft: OptionDraft) {
    editing_index = index
    draft = next_draft
    error = null
    open = true
    dialog.show()
  }

  export function show_add() {
    show(null, blank_draft())
  }

  export function show_edit(index: number) {
    show(index, draft_from(options[index]))
  }

  export function show_clone(index: number) {
    show(null, clone_draft(options[index]))
  }

  async function submit() {
    error = null
    const result = options_with_draft(options, editing_index, draft)
    if (result.error !== null) {
      error = new KilnError(result.error)
      submitting = false
      return
    }
    try {
      await save(result.options)
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
    ? "Add Environment Option"
    : "Edit Environment Option"}
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
        id="environment_option_name"
        bind:value={draft.name}
        max_length={120}
        placeholder="e.g. Acme Tech"
      />
      <div class="flex flex-col gap-2">
        <FormElement
          label="Reset Arguments"
          id="environment_option_reset_arguments"
          description="Passed to the OpenEnv's reset(). Which keys exist depends on the server."
          inputType="header_only"
          value=""
        />
        <CodeEditor
          language="json"
          min_height="160px"
          bind:value={draft.reset_arguments}
        />
      </div>
    </FormContainer>
  {/if}
</Dialog>
