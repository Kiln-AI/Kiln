<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { model_from_schema_string } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    typed_json_from_schema_model,
    type SchemaModelProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"

  let id = "plaintext_input_" + Math.random().toString(36).substring(2, 15)

  export let input_schema: string | null | undefined
  let plaintext_input: string = ""
  let structured_input_data: Record<string, string> = {}

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
  export function get_structured_input_data(): Record<string, unknown> | null {
    if (!input_schema || !structured_input_model) {
      return null
    }

    // Create a copy of structured_input_data and remove empty string values
    const cleanedData = Object.fromEntries(
      Object.entries(structured_input_data).filter((v) => v[1] !== ""),
    )

    return typed_json_from_schema_model(structured_input_model, cleanedData)
  }

  export function clear_input() {
    plaintext_input = ""
    structured_input_data = {}
  }

  export function describe_type(property: SchemaModelProperty): string {
    let base_description = ""
    if (property.type === "string") {
      base_description = "String"
    } else if (property.type === "number") {
      base_description = "Number"
    } else if (property.type === "integer") {
      base_description = "Integer"
    } else if (property.type === "boolean") {
      base_description = "'true' or 'false'"
    } else if (property.type === "array") {
      base_description = "JSON Array"
    } else if (property.type === "object") {
      base_description = "JSON Object"
    } else {
      base_description = "Unknown type"
    }

    if (property.required) {
      return base_description + " (required)"
    }
    return base_description + " (optional)"
  }

  function get_input_type(property: SchemaModelProperty): "textarea" | "input" {
    const types = ["string", "array", "object"]
    if (types.includes(property.type)) {
      return "textarea"
    }
    return "input"
  }

  function get_info_description(
    property: SchemaModelProperty,
  ): string | undefined {
    if (property.type === "array") {
      return "A list of items in JSON format. For example: [item_1, item_2]"
    }
    if (property.type === "object") {
      return 'A JSON object. For example: {"key_1": "value_1", "key_2": "value_2"}'
    }
    return undefined
  }
</script>

{#if !input_schema}
  <FormElement
    label="Plaintext Input"
    inputType="textarea"
    tall={true}
    {id}
    bind:value={plaintext_input}
  />
{:else if structured_input_model?.properties}
  {#each structured_input_model.properties as property}
    <FormElement
      id={id + "_" + property.id}
      label={property.title}
      inputType={get_input_type(property)}
      info_description={get_info_description(property)}
      info_msg={describe_type(property)}
      description={property.description}
      optional={!property.required}
      bind:value={structured_input_data[property.id]}
    />
  {/each}
{:else}
  <p>Invalid or unsupported input schema</p>
{/if}
