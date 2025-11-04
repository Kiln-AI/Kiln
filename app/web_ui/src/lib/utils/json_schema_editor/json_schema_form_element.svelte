<script lang="ts">
  import FormElement from "../form_element.svelte"
  import {
    type SchemaModelProperty,
    type SchemaModelTypedObject,
    schema_from_model,
  } from "$lib/utils/json_schema_editor/json_schema_templates"
  import Dialog from "$lib/ui/dialog.svelte"
  import JsonSchemaObject from "./json_schema_object.svelte"

  let id = Math.random().toString(36)

  // Two parallel models in this component
  // SchemaModel is the model for the visual editor
  // raw_schema is the string for the raw editor
  // raw is a flag to indicate which model is active
  export let raw = false
  export let schema_model: SchemaModelTypedObject
  export let raw_schema: string = ""

  // Accessor for the schema string. Not reactive because it's quite complex mapping two nested VMs to string and back.
  export function get_schema_string(name: string): string {
    if (raw) {
      return raw_schema
    } else {
      validate_schema(schema_model, [name])
      return JSON.stringify(schema_from_model(schema_model, true))
    }
  }

  function validate_schema(schema_model: SchemaModelProperty, path: string[]) {
    // Validate against some rules we have for our UI builder
    // to generate reasonable models (no enums with no values, no objects with no properties, etc)

    if (schema_model.type === "object") {
      if (!schema_model.properties || schema_model.properties.length === 0) {
        throw new Error(
          `Object schema must have at least one property: ${path.join(".")}`,
        )
      }
      if (schema_model.properties) {
        for (let i = 0; i < schema_model.properties.length; i++) {
          const property = schema_model.properties[i]
          const location_name = property.title
            ? property.title.toLowerCase().replace(/ /g, "_")
            : `property_${i}`
          validate_schema(property, [...path, location_name])
        }
      }
    }

    if (schema_model.enum) {
      if (schema_model.type !== "string") {
        throw new Error(`Enum must be on a string type: ${path.join(".")}`)
      }
      if (!Array.isArray(schema_model.enum)) {
        throw new Error(`Enum must be an array: ${path.join(".")}`)
      }
      if (schema_model.enum.length < 2) {
        throw new Error(`Enum must have at least two values: ${path.join(".")}`)
      }
      if (schema_model.enum.some((value) => typeof value !== "string")) {
        throw new Error(`Enum values must be strings: ${path.join(".")}`)
      }
    }
  }

  let raw_json_schema_dialog: Dialog | null = null

  function switch_to_raw_schema(): boolean {
    raw = true

    // Convert the schema model to a pretty JSON Schema string
    const json_schema_format = schema_from_model(schema_model, true)
    raw_schema = JSON.stringify(json_schema_format, null, 2)

    // Close the dialog
    return true
  }

  function switch_to_visual_schema() {
    if (
      confirm(
        "Revert to the visual schema editor?\n\nChanges made to the raw JSON schema will be lost.",
      )
    ) {
      raw = false
    }
  }

  function show_raw_json_schema_dialog() {
    raw_json_schema_dialog?.show()
  }
</script>

{#if !raw}
  <JsonSchemaObject
    {schema_model}
    on:show-raw-json-schema={show_raw_json_schema_dialog}
  />
{:else}
  <div class="flex flex-col gap-4 pt-6" {id}>
    <FormElement
      id={"raw_schema"}
      label="Raw JSON Schema"
      info_description="See json-schema.org for more information on the JSON Schema spec."
      inputType="textarea"
      height="large"
      bind:value={raw_schema}
    />
    <button
      class="link text-gray-500 text-sm text-right"
      on:click={() => switch_to_visual_schema()}>Revert to Visual Editor</button
    >
  </div>
{/if}

<Dialog
  bind:this={raw_json_schema_dialog}
  title="Not Supported by the Visual Editor"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Switch to Raw JSON Schema", action: switch_to_raw_schema },
  ]}
>
  <h4 class="mt-4">Switch to Raw JSON Schema?</h4>

  <div class="text-sm font-light text-gray-500">
    <a href="https://json-schema.org/learn" target="_blank" class="link"
      >Raw JSON Schema</a
    > will give you more control over the structure of your data, including arrays,
    nested objects, enums and more.
  </div>
  <h4 class="mt-4">Advanced Users Only</h4>
  <div class="text-sm font-light text-gray-500 mt-1">
    Raw JSON Schema provides advanced functionality, but requires technical
    expertise. Invalid schemas will cause task failures.
  </div>
</Dialog>
