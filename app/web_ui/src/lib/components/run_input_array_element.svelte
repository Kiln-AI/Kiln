<script lang="ts">
  import FormList from "$lib/utils/form_list.svelte"
  import RunInputFormElement from "./run_input_form_element.svelte"
  import RunInputFormElementRefCapture from "./run_input_form_element_ref_capture.svelte"
  import { type SchemaModelProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

  export let property: SchemaModelProperty
  export let onInputChange: (() => void) | null = null
  export let level: number = 0
  export let path: string = ""
  export let parentOptional: boolean = false
  let content: unknown[] = []

  let arrayComponents: RunInputFormElement[] = []

  export function buildArrayValue(): unknown[] | undefined {
    if (content.length === 0) {
      if (property.required) {
        return []
      } else {
        return undefined
      }
    }

    const values: unknown[] = []
    for (const [_, arrayComponent] of arrayComponents.entries()) {
      const arrayValue = arrayComponent.buildValue()
      if (arrayValue !== undefined) {
        values.push(arrayValue)
      }
    }
    return values
  }

  function getItemProperty(item_index: number): SchemaModelProperty {
    const item_path = path + "[" + item_index + "]"
    const item_title = property.title + "[" + item_index + "]"
    if (property.items) {
      // make a copy, mutating the id and title
      const item_property: SchemaModelProperty = { ...property.items }
      item_property.id = item_path
      item_property.title = item_title
      // No such thing as an optional array item
      item_property.required = true
      return item_property
    }
    // No 'items' is allowed by JSON schema. We will fall back to showing our general purpose JSON object option
    return {
      id: item_path,
      title: item_title,
      type: "object",
      additionalProperties: true,
      required: true,
    }
  }
</script>

<FormList
  content_label={property.title}
  start_with_one={false}
  bind:content
  hide_item_header={true}
>
  <div slot="default" let:item_index>
    <!-- No 'items' is allowed by JSON schema. We show our general purpose JSON object option -->
    <RunInputFormElementRefCapture
      property={getItemProperty(item_index)}
      {onInputChange}
      hideHeaderAndIndent={false}
      level={level + 1}
      path={path + "[" + item_index + "]"}
      parentOptional={parentOptional || !property.required}
      on:ref={(e) => {
        const { inst } = e.detail
        if (inst instanceof RunInputFormElement) {
          arrayComponents[item_index] = inst
        }
      }}
    />
  </div>
</FormList>
