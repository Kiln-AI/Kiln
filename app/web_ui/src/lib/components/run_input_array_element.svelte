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
</script>

<FormList content_label={property.title} start_with_one={false} bind:content>
  <div slot="default" let:item_index>
    {@const propterty_id = path + "[" + item_index + "]"}
    <!-- No 'items' is allowed by JSON schema. We show our general purpose JSON object option -->
    <RunInputFormElementRefCapture
      property={property.items || {
        id: propterty_id,
        title: property.title,
        type: "object",
        additionalProperties: true,
        required: true,
      }}
      {onInputChange}
      hideHeaderAndIndent={true}
      level={level + 1}
      path={propterty_id}
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
