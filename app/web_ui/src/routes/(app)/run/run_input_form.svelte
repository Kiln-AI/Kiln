<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import RunInputFormElement from "$lib/components/run_input_form_element.svelte"
  import { model_from_schema_string, type JsonSchema } from "$lib/utils/json_schema_editor/json_schema_templates"

  let id = "plaintext_input_" + Math.random().toString(36).substring(2, 15)

  export let input_schema: string | null | undefined
  export let onInputChange: (() => void) | null = null
  let plaintext_input: string = ""
  let structured_input_data: Record<string, unknown> = {}

  $: void (plaintext_input, structured_input_data, onInputChange?.())

  $: structured_input_model = input_schema
    ? model_from_schema_string(input_schema)
    : null

  $: fullSchema = input_schema
    ? (JSON.parse(input_schema) as JsonSchema)
    : null

  // Initialize structured_input_data with proper object structure
  $: if (structured_input_model?.properties && Object.keys(structured_input_data).length === 0) {
    const initialData: Record<string, unknown> = {}
    structured_input_model.properties.forEach(property => {
      if (property.type === "object") {
        initialData[property.id] = {}
      } else if (property.type === "array") {
        initialData[property.id] = []
      } else {
        initialData[property.id] = ""
      }
    })
    structured_input_data = initialData
  }

  // These two are mutually exclusive. One returns null if the other is not null.
  export function get_plaintext_input_data(): string | null {
    if (input_schema) {
      return null
    }
    return plaintext_input
  }

  export function get_structured_input_data(): Record<string, unknown> | null {
    if (!input_schema || !structured_input_model) {
      return null
    }

    // Clean up the data by removing empty optional objects and arrays
    const cleanedData = cleanStructuredData(structured_input_data, structured_input_model)

    return cleanedData
  }

  export function clear_input() {
    plaintext_input = ""
    structured_input_data = {}
  }

  function cleanStructuredData(
    data: Record<string, unknown>,
    model: { properties: Array<{ id: string; type: string; required: boolean }> }
  ): Record<string, unknown> {
    const cleaned: Record<string, unknown> = {}

    model.properties.forEach(property => {
      const value = data[property.id]

      if (value === undefined || value === null) {
        return // Skip undefined/null values
      }

      if (property.type === "object" && typeof value === "object") {
        if (isObjectEmpty(value)) {
          // Omit empty optional objects
          return
        }
        cleaned[property.id] = value
      } else if (property.type === "array" && Array.isArray(value)) {
        if (isArrayEmpty(value)) {
          // Omit empty optional arrays
          return
        }
        cleaned[property.id] = value
      } else if (typeof value === "string" && value === "") {
        if (!property.required) {
          // Omit empty optional strings
          return
        }
        cleaned[property.id] = value
      } else {
        cleaned[property.id] = value
      }
    })

    return cleaned
  }

  function isObjectEmpty(obj: unknown): boolean {
    if (!obj || typeof obj !== 'object') return true
    return Object.keys(obj as Record<string, unknown>).length === 0
  }

  function isArrayEmpty(arr: unknown[]): boolean {
    if (!Array.isArray(arr)) return true
    if (arr.length === 0) return true
    if (arr.length === 1) {
      const item = arr[0]
      if (typeof item === 'object' && item !== null) {
        return isObjectEmpty(item)
      }
    }
    return false
  }
</script>

{#if !input_schema}
  <FormElement
    label="Plaintext Input"
    inputType="textarea"
    height="large"
    {id}
    bind:value={plaintext_input}
  />
{:else if structured_input_model?.properties}
  {#each structured_input_model.properties as property}
    <RunInputFormElement
      property={property}
      bind:value={structured_input_data[property.id]}
      onInputChange={onInputChange}
      level={0}
      path={property.id}
      fullSchema={fullSchema}
    />
  {/each}
{:else}
  <p>Invalid or unsupported input schema</p>
{/if}
