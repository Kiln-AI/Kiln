<script lang="ts">
  // Structured manual-entry dialog for JSON-schema tasks. Reuses the Run
  // page's schema-driven form so users enter values per-property instead of
  // dumping JSON into a textarea. Output is serialized to a JSON string so it
  // funnels into the same `text` field as other entries.
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import RunInputFormElement from "$lib/components/run_input_form_element.svelte"
  import {
    model_from_schema_string,
    type SchemaModelProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"

  export let input_json_schema: string

  let dialog: Dialog | null = null
  let formKey = 0
  let rootFormElement: { buildValue(): unknown } | null = null
  let submit_error: string | null = null

  $: structured_model = (() => {
    try {
      return model_from_schema_string(input_json_schema)
    } catch {
      return null
    }
  })() as SchemaModelProperty | null

  const dispatch = createEventDispatcher<{
    add: { text: string }
  }>()

  export function show() {
    submit_error = null
    formKey += 1
    dialog?.show()
  }

  function close() {
    dialog?.close()
    return true
  }

  async function handle_add(): Promise<boolean> {
    submit_error = null
    if (!rootFormElement) {
      submit_error = "Form not ready."
      return false
    }
    try {
      const value = rootFormElement.buildValue()
      const serialized = JSON.stringify(value, null, 2)
      dispatch("add", { text: serialized })
      close()
      return true
    } catch (e) {
      submit_error = e instanceof Error ? e.message : String(e)
      return false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  width="wide"
  title="Add Manual Entry"
  sub_subtitle="Enter a structured example matching this task's input schema."
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => close() },
    {
      label: "Add",
      asyncAction: () => handle_add(),
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    {#if !structured_model}
      <div class="text-error text-sm">
        Invalid or unsupported input schema — manual entry isn't available for
        this task.
      </div>
    {:else}
      {#key formKey}
        <RunInputFormElement
          property={structured_model}
          level={0}
          path="root"
          hideHeaderAndIndent={true}
          bind:this={rootFormElement}
        />
      {/key}
    {/if}

    {#if submit_error}
      <div class="text-error text-sm">{submit_error}</div>
    {/if}
  </div>
</Dialog>
