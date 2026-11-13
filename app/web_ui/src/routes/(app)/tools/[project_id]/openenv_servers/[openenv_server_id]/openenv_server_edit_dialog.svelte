<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { OpenEnvServer } from "$lib/types"
  import {
    OPENENV_SERVER_FIELDS,
    OPENENV_UNREACHABLE_STEPS,
    OPENENV_UNREACHABLE_TITLE,
    openenv_server_url_error,
  } from "$lib/utils/openenv"
  import {
    is_openenv_unreachable,
    openenv_server_error,
    update_openenv_server,
  } from "$lib/api/openenv_server_api"

  export let project_id: string
  export let openenv_server_id: string
  export let openenv_server: OpenEnvServer
  /** Called with the saved record after a successful Save. */
  export let after_save: (saved: OpenEnvServer) => void

  let dialog: Dialog
  // The form is only mounted while the dialog is open, so it starts from the
  // saved record and Cmd+Enter can't submit a closed dialog.
  let open = false
  let name = ""
  let description = ""
  let url = ""
  let error: KilnError | null = null
  let submitting = false

  export function show() {
    name = openenv_server.name
    description = openenv_server.description ?? ""
    url = openenv_server.url ?? ""
    error = null
    open = true
    dialog.show()
  }

  async function submit() {
    error = null
    try {
      const saved = await update_openenv_server(project_id, openenv_server_id, {
        name,
        description: description || null,
        url: url.trim(),
      })
      dialog.close()
      after_save(saved)
    } catch (e) {
      error = openenv_server_error(e)
    } finally {
      submitting = false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Edit OpenEnv Server"
  on:close={() => (open = false)}
>
  {#if open}
    <FormContainer
      submit_label="Save"
      on:submit={submit}
      bind:submitting
      error={is_openenv_unreachable(error) ? null : error}
    >
      <FormElement
        label={OPENENV_SERVER_FIELDS.name.label}
        id="openenv_server_edit_name"
        description={OPENENV_SERVER_FIELDS.name.description}
        bind:value={name}
        max_length={120}
      />
      <FormElement
        label={OPENENV_SERVER_FIELDS.description.label}
        inputType="textarea"
        id="openenv_server_edit_description"
        description={OPENENV_SERVER_FIELDS.description.description}
        optional={true}
        bind:value={description}
      />
      <FormElement
        label={OPENENV_SERVER_FIELDS.url.label}
        id="openenv_server_edit_url"
        description={OPENENV_SERVER_FIELDS.url.description}
        placeholder={OPENENV_SERVER_FIELDS.url.placeholder}
        validator={openenv_server_url_error}
        bind:value={url}
      />
      {#if error && is_openenv_unreachable(error)}
        <ErrorDetailsBlock
          title={OPENENV_UNREACHABLE_TITLE}
          error_messages={error.getErrorMessages()}
          troubleshooting_steps={OPENENV_UNREACHABLE_STEPS}
        />
      {/if}
    </FormContainer>
  {/if}
</Dialog>
