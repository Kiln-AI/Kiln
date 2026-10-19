<script lang="ts">
  import Dialog from "./dialog.svelte"
  import DeleteDialog from "./delete_dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "./warning.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { base_url } from "$lib/api_client"

  export let name: string
  export let subtitle: string | undefined = undefined
  export let warning: string | undefined = undefined
  export let patch_url: string
  export let delete_url: string | undefined = undefined
  export let after_save: () => void = () => {
    // The parent page can override this, but reload the page by default
    window.location.reload()
  }
  export let after_delete: (() => void) | undefined = undefined

  type EditField = {
    label: string
    api_name: string
    value: string
    input_type: "input" | "textarea"
    description?: string
    info_description?: string
    placeholder?: string
    optional?: boolean
    max_length?: number
    // When set, this field is excluded from the main PATCH body and persisted via this
    // callback instead (e.g. fields that target a different endpoint). Fields sharing a
    // setter are saved in one call, with their values keyed by api_name.
    custom_setter?: (values: Record<string, string>) => Promise<void>
  }
  export let fields: EditField[]

  let error: KilnError | null = null
  let loading = false
  let saved = false

  async function save() {
    loading = true
    try {
      // Custom setters run first: if one fails, the main PATCH hasn't been sent yet.
      const custom_setter_values = new Map<
        (values: Record<string, string>) => Promise<void>,
        Record<string, string>
      >()
      for (const field of fields) {
        if (field.custom_setter) {
          const values = custom_setter_values.get(field.custom_setter) || {}
          values[field.api_name] = field.value
          custom_setter_values.set(field.custom_setter, values)
        }
      }
      for (const [custom_setter, values] of custom_setter_values) {
        await custom_setter(values)
      }

      const body = fields.reduce(
        (acc, field) => {
          if (!field.custom_setter) {
            acc[field.api_name] = field.value
          }
          return acc
        },
        {} as Record<string, string>,
      )
      if (Object.keys(body).length > 0) {
        const response = await fetch(base_url + patch_url, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        })
        if (!response.ok) {
          let error_body: unknown
          try {
            error_body = await response.json()
          } catch (_) {
            throw new Error("Failed to save edit. Invalid JSON response.")
          }
          throw createKilnError(error_body)
        }
      }
      after_save()
      saved = true
      // Unsetting lets us re-save
      setTimeout(() => {
        saved = false
      }, 3000)
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  let dialog: Dialog | null = null
  export function show() {
    dialog?.show()
  }

  export function close() {
    dialog?.close()
  }

  let delete_dialog: DeleteDialog | null = null
  function showDeleteDialog() {
    dialog?.close()
    delete_dialog?.show()
  }
</script>

<Dialog
  title={"Edit " + name}
  bind:this={dialog}
  header_buttons={delete_url
    ? [
        {
          image_path: "/images/delete.svg",
          alt_text: "Delete",
          action: () => showDeleteDialog(),
        },
      ]
    : []}
>
  {#if subtitle}
    <div class="text-sm font-light text-gray-500">{subtitle}</div>
  {/if}
  {#if warning}
    <div class="mt-6">
      <Warning
        warning_message={warning}
        warning_color="warning"
        warning_icon="info"
      />
    </div>
  {/if}
  <div class="mt-6">
    <FormContainer
      submit_label="Save"
      {error}
      on:submit={save}
      submitting={loading}
      bind:saved
    >
      {#each fields as field}
        <FormElement
          bind:value={field.value}
          id={field.api_name}
          label={field.label}
          description={field.description}
          inputType={field.input_type}
          info_description={field.info_description}
          placeholder={field.placeholder}
          optional={field.optional}
          max_length={field.max_length}
        />
      {/each}
    </FormContainer>
  </div>
</Dialog>

{#if delete_url}
  <DeleteDialog
    bind:this={delete_dialog}
    {name}
    {delete_url}
    after_delete={after_delete || after_save}
  />
{/if}
