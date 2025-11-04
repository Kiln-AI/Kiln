<script lang="ts">
  import FormElement from "../form_element.svelte"
  import {
    type SchemaModelProperty,
    type SchemaModelTypedObject,
  } from "./json_schema_templates"
  import { createEventDispatcher } from "svelte"
  import JsonSchemaObject from "./json_schema_object.svelte"

  const dispatch = createEventDispatcher()

  let id = Math.random().toString(36)
  export let model: SchemaModelProperty = {
    id: "",
    title: "",
    description: "",
    type: "string",
    required: true,
  }
  let type_option:
    | "string"
    | "number"
    | "integer"
    | "boolean"
    | "array"
    | "object"
    | "enum" = "string"

  let enum_text: string = ""

  let object_model: SchemaModelTypedObject | undefined = undefined
  $: object_model =
    model.type === "object" && model.properties
      ? (model as SchemaModelTypedObject)
      : undefined

  // We have some types in the drop down we don't actually support.
  // When selected, we want to show the raw JSON Schema modal to give users a choice.
  // TODO reduce this list
  const unsupported_types = ["array", "other"]
  function selected_type(e: Event) {
    const target = e.target as HTMLSelectElement
    const value = target.value

    if (unsupported_types.includes(value)) {
      // Block actually changing the type, keep the old value which should be valid
      const prior_value = model.type
      target.value = prior_value

      // Show the dialog so the user can choose
      dispatch("show-raw-json-schema")
    }
  }

  function type_changed(
    new_type:
      | "string"
      | "number"
      | "integer"
      | "boolean"
      | "array"
      | "object"
      | "enum",
  ) {
    // Setup properties for object type (or clear if not supported)
    if (new_type === "object") {
      model.properties = model.properties ?? []
    } else {
      model.properties = undefined
    }

    // Setup enum for enum type
    // enums are special var on string type, not their own type
    if (new_type === "enum") {
      model.enum = model.enum ?? []
      model.type = "string"
    } else {
      model.enum = undefined
      model.type = new_type
    }

    // Trigger reactivity
    model = model
  }
  $: type_changed(type_option)

  function add_enum_value() {
    const trimmed_text = enum_text.trim()
    if (trimmed_text === "") {
      return
    }

    if (!model.enum?.includes(trimmed_text)) {
      model.enum?.push(trimmed_text)
    }
    enum_text = ""
    model = model
  }

  function remove_enum_value(value: unknown) {
    model.enum = model.enum?.filter((v) => v !== value)
    model = model
  }
</script>

<div class="flex flex-row gap-3">
  <div class="grow">
    <FormElement
      id={"property_" + id + "_title"}
      label="Property Name"
      inputType="input"
      bind:value={model.title}
      light_label={true}
    />
  </div>
  <FormElement
    id={"property_" + id + "_type"}
    label="Type"
    inputType="select"
    bind:value={type_option}
    on_select={(e) => selected_type(e)}
    select_options={[
      ["string", "String"],
      ["number", "Number"],
      ["integer", "Integer"],
      ["boolean", "Boolean"],
      ["array", "Array"],
      ["object", "Object"],
      ["enum", "Enum"],
      ["other", "More..."],
    ]}
    light_label={true}
  />
  <FormElement
    id={"property_" + id + "_required"}
    label="Required"
    inputType="select"
    bind:value={model.required}
    select_options={[
      [true, "True"],
      [false, "False"],
    ]}
    light_label={true}
  />
</div>
<FormElement
  id={"property_" + id + "_description"}
  label="Description"
  inputType="input"
  bind:value={model.description}
  light_label={true}
/>

<!-- Per type fields -->

{#if object_model}
  <div class="ml-4 pl-4 border-l">
    <JsonSchemaObject bind:schema_model={object_model} />
  </div>
{/if}

{#if type_option === "enum"}
  <div class="flex flex-row gap-3">
    <div class="w-64">
      <FormElement
        id={"property_" + id + "_enum"}
        label="Enum Values"
        inputType="input"
        optional={true}
        info_msg=" "
        placeholder="Enter a value"
        bind:value={enum_text}
        light_label={true}
      />
    </div>
    <div class="mt-5 flex flex-row gap-6 grow">
      <button
        class="btn btn-primary"
        on:click={add_enum_value}
        disabled={enum_text.trim() === ""}>Add</button
      >
      <div
        class="flex flex-row flex-wrap grow gap-1 place-content-center items-center"
      >
        {#each model.enum ?? [] as value}
          <button
            class="badge badge-outline"
            on:click={() => remove_enum_value(value)}
          >
            {value}
            <span class="pl-2">&times;</span>
          </button>
        {/each}
      </div>
    </div>
  </div>
{/if}
