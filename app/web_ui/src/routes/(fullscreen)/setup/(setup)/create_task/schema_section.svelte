<script lang="ts">
  import JsonSchemaFormElement from "$lib/utils/json_schema_editor/json_schema_form_element.svelte"
  import {
    example_schema_model,
    model_from_schema,
    type SchemaModelProperty,
    type SchemaModelType,
    type SchemaModelTypedObject,
  } from "$lib/utils/json_schema_editor/json_schema_templates"

  let id = Math.random().toString(36)
  export let warn_about_required: boolean = false

  // Not the best svelte bindings here.
  // We're reactive for setting the schema_string, which allows the caller to set a well known schema (like the demo/example)
  // It's not reactive when the user starts editing (the string stays static), as we need a more complex in memory view-model. Access the new string via the accessor below.
  export let schema_string: string | null = null

  // The visual editor can only represent a subset of JSON Schema: a typed object
  // with additionalProperties:false, single-type properties, etc. Schemas authored
  // via the API or the raw JSON editor often fall outside that subset (union types,
  // open objects, camelCase keys, missing root additionalProperties). For those we
  // fall back to the raw JSON editor instead of crashing, so the schema is preserved
  // verbatim and stays editable (e.g. when cloning such a task).
  let schema_model: SchemaModelTypedObject = example_schema_model()
  let plaintext: boolean = !schema_string

  // Keep the raw state here, so it persists even if they toggle the radio back to plaintext, and the component is removed.
  let raw = false
  let raw_schema_string: string = ""

  $: load_schema(schema_string)

  // Load the schema string into the editor. Supported schemas open in the visual
  // editor; anything the visual editor can't represent opens in the raw editor.
  function load_schema(new_schema_string: string | null) {
    plaintext = !new_schema_string
    if (!new_schema_string) {
      schema_model = example_schema_model()
      raw = false
      raw_schema_string = ""
      return
    }
    const model = typed_object_from_string(new_schema_string)
    if (model) {
      schema_model = model
      raw = false
      raw_schema_string = ""
    } else {
      raw = true
      raw_schema_string = new_schema_string
    }
  }

  // Parse a schema string into the visual editor's view-model, or return null if
  // it isn't a typed object the visual editor supports.
  function typed_object_from_string(
    new_schema_string: string,
  ): SchemaModelTypedObject | null {
    try {
      const model = model_from_schema(JSON.parse(new_schema_string))
      // Check it's a valid object with properties (aka SchemaModelTypedObject) -- we only support typed objects for now
      if (
        model.type === "object" &&
        model.properties &&
        model.additionalProperties === false &&
        representable_in_visual_editor(model)
      ) {
        return model as SchemaModelTypedObject
      }
    } catch {
      // Invalid JSON or unsupported shape -- fall back to the raw editor.
    }
    return null
  }

  const REPRESENTABLE_TYPES: SchemaModelType[] = [
    "number",
    "string",
    "integer",
    "boolean",
    "array",
    "object",
  ]

  // The visual editor models each property's type as a single primitive. A node
  // with a union type (e.g. ["string", "null"]) or any other non-primitive type
  // can't be represented and would be silently mangled on save -- so recurse and
  // bail to the raw editor if any node (root or nested) has an unsupported type.
  function representable_in_visual_editor(model: SchemaModelProperty): boolean {
    if (!(REPRESENTABLE_TYPES as string[]).includes(model.type)) {
      return false
    }
    if (model.items && !representable_in_visual_editor(model.items)) {
      return false
    }
    if (model.properties) {
      return model.properties.every(representable_in_visual_editor)
    }
    return true
  }

  let schema_form_element: JsonSchemaFormElement | null = null

  export function get_schema_string(name: string): string | null {
    if (plaintext) {
      return null
    }
    return schema_form_element?.get_schema_string(name) || null
  }
</script>

<div>
  <div class="form-control">
    <label class="label cursor-pointer flex flex-row gap-3">
      <input
        type="radio"
        name="radio-input-schema-{id}"
        class="radio"
        value={true}
        bind:group={plaintext}
      />
      <span class="label-text text-left grow">Plain Text</span>
    </label>
  </div>
  <div class="form-control">
    <label class="label cursor-pointer flex flex-row gap-3">
      <input
        type="radio"
        name="radio-input-schema-{id}"
        class="radio"
        value={false}
        bind:group={plaintext}
      />
      <span class="label-text text-left grow">Structured JSON</span>
    </label>
  </div>

  {#if !plaintext}
    <JsonSchemaFormElement
      bind:this={schema_form_element}
      {schema_model}
      bind:raw_schema={raw_schema_string}
      bind:raw
      {warn_about_required}
    />
  {/if}
</div>
