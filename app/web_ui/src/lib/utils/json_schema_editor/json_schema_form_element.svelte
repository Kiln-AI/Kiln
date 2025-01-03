<script lang="ts">
  import FormElement from "../form_element.svelte"
  import {
    type SchemaModel,
    schema_from_model,
  } from "$lib/utils/json_schema_editor/json_schema_templates"

  let validation_errors: string[] = []
  let id = Math.random().toString(36)

  // Two parallel models in this component
  // SchemaModel is the model for the visual editor
  // raw_schema is the string for the raw editor
  // raw is a flag to indicate which model is active
  export let raw = false
  export let schema_model: SchemaModel
  export let raw_schema: string = ""

  // Accessor for the schema string. Not reactive because it's quite complex mapping two nested VMs to string and back.
  export function get_schema_string(): string {
    if (raw) {
      return raw_schema
    } else {
      return JSON.stringify(schema_from_model(schema_model))
    }
  }

  async function add_property() {
    schema_model.properties.push({
      id: "",
      title: "",
      description: "",
      type: "string",
      required: true,
    })
    // Trigger reactivity
    schema_model = schema_model
    // Scroll new item into view. Async to allow rendering first
    setTimeout(() => {
      const property = document.getElementById(
        "property_" + (schema_model.properties.length - 1) + "_" + id,
      )
      if (property) {
        property.scrollIntoView({ block: "center" })
      }
    }, 1)
  }

  function remove_property(index: number) {
    const property = schema_model.properties[index]
    const isPropertyEdited = property.title || property.description

    if (
      !isPropertyEdited ||
      confirm(
        "Are you sure you want to remove Property #" +
          (index + 1) +
          "?\n\nIt has content which hasn't been saved.",
      )
    ) {
      schema_model.properties.splice(index, 1)
      // trigger reactivity
      schema_model = schema_model
      // Move the page to the top anchor
      const list = document.getElementById(id)
      if (list) {
        // Scroll to the top of the list
        setTimeout(() => {
          list.scrollIntoView()
        }, 1)
      }
    }
  }

  // We have some types in the drop down we don't actually support.
  // When selected, we want to show the raw JSON Schema modal to give users a choice.
  const unsupported_types = ["array", "object", "enum", "other"]
  function selected_type(e: Event, index: number) {
    const target = e.target as HTMLSelectElement
    const value = target.value
    if (!unsupported_types.includes(value)) {
      // This type is supported, all good
      return
    }

    // Block actually changing the type, keep the old value which should be valid
    const prior_value = schema_model.properties[index].type
    target.value = prior_value

    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("raw_json_schema_modal")?.showModal()
  }

  function switch_to_raw_schema() {
    raw = true

    // Convert the schema model to a pretty JSON Schema string
    const json_schema_format = schema_from_model(schema_model)
    raw_schema = JSON.stringify(json_schema_format, null, 2)

    // @ts-expect-error close is not a method on HTMLElement
    document.getElementById("raw_json_schema_modal")?.close()
  }
</script>

{#if !raw}
  {#if validation_errors.length > 0}
    <div class="validation-errors">
      {#each validation_errors as error}
        <div class="text-error">{error}</div>
      {/each}
    </div>
  {:else}
    <div class="flex flex-col gap-8 pt-6" {id}>
      {#each schema_model.properties as property, index}
        {#if property}
          <!-- ignore that we don't use this var-->
        {/if}

        <div class="flex flex-col gap-2">
          <div
            class="flex flex-row gap-3 font-medium text-sm pb-2"
            id={"property_" + index + "_" + id}
          >
            <div class="grow">
              Property #{index + 1}
            </div>
            <button
              class="link text-xs text-gray-500"
              on:click={() => remove_property(index)}
            >
              remove
            </button>
          </div>
          <div class="flex flex-row gap-3">
            <div class="grow">
              <FormElement
                id={"property_" + property.id + "_title"}
                label="Property Name"
                inputType="input"
                bind:value={schema_model.properties[index].title}
                light_label={true}
              />
            </div>
            <FormElement
              id={"property_" + property.id + "_type"}
              label="Type"
              inputType="select"
              bind:value={schema_model.properties[index].type}
              on_select={(e) => selected_type(e, index)}
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
              id={"property_" + property.id + "_required"}
              label="Required"
              inputType="select"
              bind:value={schema_model.properties[index].required}
              select_options={[
                [true, "True"],
                [false, "False"],
              ]}
              light_label={true}
            />
          </div>
          <FormElement
            id={"property_" + property.id + "_description"}
            label="Description"
            inputType="input"
            bind:value={schema_model.properties[index].description}
            light_label={true}
          />
        </div>
      {/each}
      <div class="flex place-content-center">
        <button
          class="btn btn-sm"
          on:click={() => add_property()}
          id={"add_button_" + id}
        >
          Add Property
        </button>
      </div>
    </div>
  {/if}
{:else}
  <div class="flex flex-col gap-8 pt-6" {id}>
    <FormElement
      id={"raw_schema"}
      label="Raw JSON Schema"
      info_description="See json-schema.org for more information on the JSON Schema spec."
      inputType="textarea"
      tall={true}
      bind:value={raw_schema}
    />
  </div>
{/if}

<dialog id="raw_json_schema_modal" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-medium mb-1">
      Not Supported by our Visual Editor.
    </h3>
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
    <div class="flex flex-row gap-2 justify-end mt-6">
      <form method="dialog">
        <button class="btn btn-sm h-10 btn-outline min-w-24">Cancel</button>
      </form>
      <button
        class="btn btn-sm h-10 min-w-24 btn-secondary"
        on:click={switch_to_raw_schema}
      >
        Switch to Raw JSON Schema
      </button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
