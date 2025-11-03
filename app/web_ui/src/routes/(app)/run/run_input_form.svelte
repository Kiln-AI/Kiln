<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import RunInputFormElement from "$lib/components/run_input_form_element.svelte"
  import {
    model_from_schema_string,
    type SchemaModelProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"

  let id = "plaintext_input_" + Math.random().toString(36).substring(2, 15)

  export let input_schema: string | null | undefined
  export let onInputChange: (() => void) | null = null
  let plaintext_input: string = ""

  // Store ref to the root form element
  let rootFormElement: { buildValue(): unknown } | null = null

  $: void onInputChange?.()

  let structured_input_model: SchemaModelProperty | null = null
  $: structured_input_model = input_schema
    ? model_from_schema_string(input_schema)
    : null

  // These two are mutually exclusive. One returns null if the other is not null.
  export function get_plaintext_input_data(): string | null {
    if (input_schema) {
      return null
    }
    return plaintext_input
  }

  export function clear_input() {
    plaintext_input = ""
    rootFormElement = null
  }

  // TODO
  let builtValue: unknown = "undset"
  let err: unknown | null = null
</script>

{#if !input_schema}
  <FormElement
    label="Plaintext Input"
    inputType="textarea"
    height="large"
    {id}
    bind:value={plaintext_input}
  />
{:else if structured_input_model}
  <RunInputFormElement
    property={structured_input_model}
    {onInputChange}
    level={0}
    path="root"
    hideHeaderAndIndent={true}
    bind:this={rootFormElement}
  />
{:else}
  <p>Invalid or unsupported input schema</p>
{/if}

<!-- TODO -->
<div>
  <button
    class="btn btn-primary"
    on:click={() => {
      console.info("builtValue", builtValue)
      try {
        builtValue = rootFormElement?.buildValue()
        err = null
        if (builtValue === undefined) {
          err = new Error("Built value is undefined")
        }
      } catch (error) {
        err = error
        builtValue = undefined
      }
    }}>Build Value</button
  >
  <pre>{JSON.stringify(builtValue, null, 2)}</pre>
  <div class="text-red-500">{err ? err.toString() : ""}</div>
</div>
