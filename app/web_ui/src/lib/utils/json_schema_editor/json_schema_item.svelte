<script lang="ts">
  import FormElement from "../form_element.svelte"
  import {
    type SchemaModelProperty,
    type SchemaModelTypedObject,
    type SchemaModelType,
  } from "./json_schema_templates"
  import { createEventDispatcher, tick } from "svelte"
  import JsonSchemaObject from "./json_schema_object.svelte"

  const dispatch = createEventDispatcher()

  export let warn_about_required: boolean = false

  let id = Math.random().toString(36)
  export let model: SchemaModelProperty = {
    id: "",
    title: "",
    description: "",
    type: "string",
    required: true,
  }

  // Enum is UI only type, not in JSON schema as .type
  type TypeOption = SchemaModelType | "enum"
  let type_option: TypeOption = "string"
  let enum_text: string = ""
  let enum_options: string[] = []
  let array_type: TypeOption = "string"
  let array_object_model: SchemaModelTypedObject | undefined = undefined

  let object_model: SchemaModelTypedObject | undefined = undefined
  $: object_model =
    model.type === "object" &&
    model.properties &&
    model.additionalProperties === false
      ? (model as SchemaModelTypedObject)
      : undefined

  // "custom" shows dialog before taking effect
  function selected_type(e: Event) {
    const target = e.target as HTMLSelectElement
    const value = target.value

    if (value === "custom") {
      // Block actually changing the type, keep the old value which should be valid
      const prior_value = model.type
      target.value = prior_value

      // Show the dialog so the user can select custom
      dispatch("show-raw-json-schema")
    }
  }

  function type_changed(new_type: TypeOption) {
    // Setup properties for object type (or clear if not supported)
    if (new_type === "object") {
      model.properties = model.properties ?? []
      model.additionalProperties = false
    } else {
      model.properties = undefined
      model.additionalProperties = undefined
    }

    // Setup enum for enum type
    // enums are special var on string type, not their own type
    enum_options = []
    if (new_type === "enum") {
      model.enum = []
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

    if (!enum_options.includes(trimmed_text)) {
      enum_options.push(trimmed_text)
    }
    enum_text = ""

    // Trigger reactivity
    enum_options = enum_options
    model = model
  }

  function remove_enum_value(value: unknown) {
    enum_options = enum_options.filter((v) => v !== value)
    model = model
  }

  function update_enum(
    type_option: TypeOption,
    array_type: TypeOption,
    enum_options: string[],
  ) {
    // Update the enum: different places based on item type
    if (type_option === "enum") {
      model.enum = enum_options
      model.type = "string"
    } else {
      model.enum = undefined
    }

    if (type_option === "array" && array_type === "enum") {
      // @ts-expect-error knowingly skipping id/title/required
      model.items = {
        type: "string",
        enum: enum_options,
      }
    }

    model = model

    // Focus on the enum input after the DOM has been updated
    if (
      type_option === "enum" ||
      (type_option === "array" && array_type === "enum")
    ) {
      tick().then(() => {
        document.getElementById("property_" + id + "_enum_input")?.focus()
      })
    }
  }
  $: update_enum(type_option, array_type, enum_options)

  // Update the moodel for array type
  function update_array_type(model_type: TypeOption, array_type: TypeOption) {
    if (model_type === "array") {
      // Enum handled above, special case with more values
      if (array_type !== "enum") {
        if (array_type === "object") {
          array_object_model = {
            id: "",
            title: "",
            required: true,
            type: "object",
            properties: [],
            additionalProperties: false,
          }
          model.items = array_object_model
        } else {
          // @ts-expect-error knowingly skipping id/title/required
          model.items = {
            type: array_type,
          }
        }
      }
    } else {
      model.items = undefined
    }
    model = model
  }
  $: update_array_type(type_option, array_type)
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
      ["custom", "Custom Schema"],
    ]}
    light_label={true}
  />
  {#if model.type === "array"}
    <FormElement
      id={"property_" + id + "_array_type"}
      label="Array Items"
      inputType="select"
      bind:value={array_type}
      select_options={[
        ["string", "String"],
        ["number", "Number"],
        ["integer", "Integer"],
        ["boolean", "Boolean"],
        ["object", "Object"],
        ["enum", "Enum"],
      ]}
      light_label={true}
    />
  {/if}
  <FormElement
    id={"property_" + id + "_required"}
    label="Required"
    inputType="fancy_select"
    bind:value={model.required}
    fancy_select_options={[
      {
        options: [
          { label: "Required", value: true },
          {
            label: "Optional",
            value: false,
            description: warn_about_required
              ? "Not supported by some providers, including OpenAI"
              : undefined,
          },
        ],
      },
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
    <JsonSchemaObject bind:schema_model={object_model} {warn_about_required} />
  </div>
{/if}

{#if array_object_model && type_option === "array" && array_type === "object"}
  <div class="ml-4 pl-4 border-l">
    <div class="text-sm text-gray-500">Array Object Schema</div>
    <JsonSchemaObject
      bind:schema_model={array_object_model}
      {warn_about_required}
    />
  </div>
{/if}

{#if type_option === "enum" || (type_option === "array" && array_type === "enum")}
  <div>
    <div class="text-xs text-gray-500 font-medium mb-1">Enum Values</div>
    <div class="flex flex-row flex-wrap grow gap-1 mb-2">
      {#if enum_options.length == 0}
        <div class="text-sm text-error">No values added</div>
      {/if}
      {#each enum_options as value}
        <button
          class="badge badge-outline"
          on:click={() => remove_enum_value(value)}
        >
          {value}
          <span class="pl-2">&times;</span>
        </button>
      {/each}
    </div>
    <div class="flex flex-row gap-2">
      <input
        id={"property_" + id + "_enum_input"}
        type="text"
        class="input input-bordered w-64"
        bind:value={enum_text}
        placeholder="Enter a value"
        on:keydown={(e) => {
          if (e.key === "Enter") {
            add_enum_value()
            e.preventDefault()
          }
        }}
      />
      <button
        class="btn btn-primary"
        on:click={add_enum_value}
        disabled={enum_text.trim() === ""}>Add</button
      >
    </div>
  </div>
{/if}
