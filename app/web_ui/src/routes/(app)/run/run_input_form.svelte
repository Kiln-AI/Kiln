<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { model_from_schema_string } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    typed_json_from_schema_model,
    type SchemaModelProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"
  import { _ } from "svelte-i18n"

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
      base_description = $_("run.type_descriptions.string")
    } else if (property.type === "number") {
      base_description = $_("run.type_descriptions.number")
    } else if (property.type === "integer") {
      base_description = $_("run.type_descriptions.integer")
    } else if (property.type === "boolean") {
      base_description = $_("run.type_descriptions.boolean")
    } else if (property.type === "array") {
      base_description = $_("run.type_descriptions.array")
    } else if (property.type === "object") {
      base_description = $_("run.type_descriptions.object")
    } else {
      base_description = $_("run.type_descriptions.unknown")
    }

    if (property.required) {
      return base_description + $_("run.type_descriptions.required_suffix")
    }
    return base_description + $_("run.type_descriptions.optional_suffix")
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
      return $_("run.input_info.array_description")
    }
    if (property.type === "object") {
      return $_("run.input_info.object_description")
    }
    return undefined
  }
</script>

{#if !input_schema}
  <FormElement
    label={$_("run.plaintext_input")}
    inputType="textarea"
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
  <p>{$_("run.invalid_unsupported_schema")}</p>
{/if}
