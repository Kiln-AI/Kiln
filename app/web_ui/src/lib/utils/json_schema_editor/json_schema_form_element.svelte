<script lang="ts">
  import FormElement from "../form_element.svelte"
  import {
    type SchemaModel,
    schema_from_model,
  } from "$lib/utils/json_schema_editor/json_schema_templates"
  import Dialog from "$lib/ui/dialog.svelte"
  import { _ } from "svelte-i18n"

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
      return JSON.stringify(schema_from_model(schema_model, true))
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
        $_("json_schema.confirm_remove_property", {
          values: { number: index + 1 },
        }),
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

  let raw_json_schema_dialog: Dialog | null = null

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

    // Show the dialog so the user can choose
    raw_json_schema_dialog?.show()
  }

  function switch_to_raw_schema(): boolean {
    raw = true

    // Convert the schema model to a pretty JSON Schema string
    const json_schema_format = schema_from_model(schema_model, true)
    raw_schema = JSON.stringify(json_schema_format, null, 2)

    // Close the dialog
    return true
  }

  function switch_to_visual_schema() {
    if (confirm($_("json_schema.confirm_revert_to_visual"))) {
      raw = false
    }
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
              {$_("json_schema.property_number", {
                values: { number: index + 1 },
              })}
            </div>
            <button
              class="link text-xs text-gray-500"
              on:click={() => remove_property(index)}
            >
              {$_("json_schema.remove")}
            </button>
          </div>
          <div class="flex flex-row gap-3">
            <div class="grow">
              <FormElement
                id={"property_" + property.id + "_title"}
                label={$_("json_schema.property_name")}
                inputType="input"
                bind:value={schema_model.properties[index].title}
                light_label={true}
              />
            </div>
            <FormElement
              id={"property_" + property.id + "_type"}
              label={$_("json_schema.type")}
              inputType="select"
              bind:value={schema_model.properties[index].type}
              on_select={(e) => selected_type(e, index)}
              select_options={[
                ["string", $_("json_schema.types.string")],
                ["number", $_("json_schema.types.number")],
                ["integer", $_("json_schema.types.integer")],
                ["boolean", $_("json_schema.types.boolean")],
                ["array", $_("json_schema.types.array")],
                ["object", $_("json_schema.types.object")],
                ["enum", $_("json_schema.types.enum")],
                ["other", $_("json_schema.types.other")],
              ]}
              light_label={true}
            />
            <FormElement
              id={"property_" + property.id + "_required"}
              label={$_("json_schema.required")}
              inputType="select"
              bind:value={schema_model.properties[index].required}
              select_options={[
                [true, $_("json_schema.required_options.true")],
                [false, $_("json_schema.required_options.false")],
              ]}
              light_label={true}
            />
          </div>
          <FormElement
            id={"property_" + property.id + "_description"}
            label={$_("json_schema.description")}
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
          {$_("json_schema.add_property")}
        </button>
      </div>
    </div>
  {/if}
{:else}
  <div class="flex flex-col gap-4 pt-6" {id}>
    <FormElement
      id={"raw_schema"}
      label={$_("json_schema.raw_json_schema")}
      info_description={$_("json_schema.raw_json_schema_info")}
      inputType="textarea"
      tall={true}
      bind:value={raw_schema}
    />
    <button
      class="link text-gray-500 text-sm text-right"
      on:click={() => switch_to_visual_schema()}
      >{$_("json_schema.revert_to_visual_editor")}</button
    >
  </div>
{/if}

<Dialog
  bind:this={raw_json_schema_dialog}
  title={$_("json_schema.not_supported_by_visual_editor")}
  action_buttons={[
    { label: $_("common.cancel"), isCancel: true },
    {
      label: $_("json_schema.switch_to_raw_json_schema"),
      action: switch_to_raw_schema,
    },
  ]}
>
  <h4 class="mt-4">{$_("json_schema.switch_to_raw_json_schema_question")}</h4>

  <div class="text-sm font-light text-gray-500">
    <a href="https://json-schema.org/learn" target="_blank" class="link"
      >{$_("json_schema.raw_json_schema")}</a
    >
    {$_("json_schema.raw_json_schema_description")}
  </div>
  <h4 class="mt-4">{$_("json_schema.advanced_users_only")}</h4>
  <div class="text-sm font-light text-gray-500 mt-1">
    {$_("json_schema.advanced_users_warning")}
  </div>
</Dialog>
