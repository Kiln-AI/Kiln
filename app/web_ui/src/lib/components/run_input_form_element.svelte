<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import RunInputFormElement from "./run_input_form_element.svelte"
  import {
    type SchemaModelProperty,
    type JsonSchema,
    type JsonSchemaProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"

  export let property: SchemaModelProperty
  export let value: unknown
  export let onInputChange: (() => void) | null = null
  export let level: number = 0
  export let path: string = ""
  export let fullSchema: JsonSchema | null = null

  let id = "nested_input_" + Math.random().toString(36).substring(2, 15)

  // Create reactive values for nested properties
  let nestedValues: Record<string, unknown> = {}
  let arrayContent: unknown[] = []

  $: {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      nestedValues = value as Record<string, unknown>
    } else if (isObjectProperty(property)) {
      nestedValues = {}
      value = nestedValues
    }

    if (Array.isArray(value)) {
      arrayContent = value
    } else if (isArrayProperty(property)) {
      arrayContent = []
      value = arrayContent
    }

    onInputChange?.()
  }

  function describe_type(property: SchemaModelProperty): string {
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
      if (isGenericArray(property)) {
        base_description = "Arbitrary JSON Array"
      } else {
        base_description = "Array"
      }
    } else if (property.type === "object") {
      if (isGenericObject(property)) {
        base_description = "Arbitrary JSON Object"
      } else {
        base_description = "Object"
      }
    } else {
      base_description = "Unknown type"
    }

    if (property.required) {
      return base_description + " (required)"
    }
    return base_description + " (optional)"
  }

  function get_input_type(
    property: SchemaModelProperty,
  ): "textarea" | "input" | "input_number" {
    if (isGenericObject(property) || isGenericArray(property)) {
      return "textarea"
    } else if (property.type === "string") {
      return "textarea"
    } else if (property.type === "number" || property.type === "integer") {
      // TODO
      return "input_number"
    }
    return "input"
  }

  function getDescription(property: SchemaModelProperty): string {
    if (isGenericObject(property)) {
      return property.description + " (JSON Object with flexible properties)"
    } else if (isGenericArray(property)) {
      return property.description + " (JSON Array with flexible item types)"
    }
    return property.description
  }

  function getHeight(property: SchemaModelProperty): "large" | undefined {
    if (isGenericObject(property) || isGenericArray(property)) {
      return "large"
    }
    return undefined
  }

  function handleInput(e: Event) {
    // TODO
    const target = e.target as HTMLInputElement | HTMLTextAreaElement
    if (target) {
      const newValue = target.value
      if (isGenericObject(property) || isGenericArray(property)) {
        try {
          JSON.parse(newValue)
          value = newValue
        } catch {
          value = newValue
        }
      } else {
        value = newValue
      }
    }
  }

  function isArrayProperty(prop: SchemaModelProperty): boolean {
    return prop.type === "array"
  }

  function isObjectProperty(prop: SchemaModelProperty): boolean {
    return prop.type === "object"
  }

  function isGenericArray(property: SchemaModelProperty): boolean {
    if (property.type !== "array") return false

    const jsonSchemaProperty = getNestedSchemaProperty(property)
    return (
      !jsonSchemaProperty?.items ||
      (typeof jsonSchemaProperty.items === "object" &&
        "type" in jsonSchemaProperty.items &&
        jsonSchemaProperty.items.type === "object" &&
        (jsonSchemaProperty.items as JsonSchemaProperty)
          .additionalProperties === true)
    )
  }

  function getNestedSchemaProperty(
    property: SchemaModelProperty,
  ): JsonSchemaProperty | null {
    if (!fullSchema) return null

    // If it's a top-level property, get it directly
    if (fullSchema.properties[property.id]) {
      return fullSchema.properties[property.id] as JsonSchemaProperty
    }

    // If it's a nested property, traverse the path to find the parent object
    if (path) {
      const pathParts = path.split(".")
      let currentSchema: JsonSchema | JsonSchemaProperty = fullSchema

      // Traverse to the parent object (excluding the current property)
      for (let i = 0; i < pathParts.length - 1; i++) {
        const part = pathParts[i]
        if (
          currentSchema.type === "object" &&
          currentSchema.properties &&
          currentSchema.properties[part]
        ) {
          currentSchema = currentSchema.properties[part]
        } else {
          return null
        }
      }

      // Get the current property from the parent schema
      const currentPropertyId = pathParts[pathParts.length - 1]
      if (
        currentSchema.type === "object" &&
        currentSchema.properties &&
        currentSchema.properties[currentPropertyId]
      ) {
        return currentSchema.properties[currentPropertyId] as JsonSchemaProperty
      }
    }

    return null
  }

  function isGenericObject(property: SchemaModelProperty): boolean {
    if (property.type !== "object") return false

    const jsonSchemaProperty = getNestedSchemaProperty(property)
    return (
      jsonSchemaProperty?.type === "object" &&
      (jsonSchemaProperty.additionalProperties === true ||
        !jsonSchemaProperty.properties ||
        Object.keys(jsonSchemaProperty.properties).length === 0)
    )
  }

  function getNestedSchemaForObject(
    property: SchemaModelProperty,
  ): SchemaModelProperty[] {
    if (property.type !== "object") return []

    const jsonSchemaProperty = getNestedSchemaProperty(property)
    if (
      jsonSchemaProperty?.type === "object" &&
      jsonSchemaProperty.properties &&
      Object.keys(jsonSchemaProperty.properties).length > 0
    ) {
      const requiredFields = jsonSchemaProperty.required || []

      return Object.entries(jsonSchemaProperty.properties).map(
        ([id, prop]: [string, JsonSchemaProperty]) => ({
          id,
          title: prop.title || id,
          description: prop.description || "",
          type: prop.type,
          required: requiredFields.includes(id),
        }),
      )
    }

    return []
  }

  function getArrayEmptyContent(): unknown {
    return ""
  }

  // Handle the nested data structure
  $: if (
    isObjectProperty(property) &&
    typeof value === "object" &&
    value !== null
  ) {
    // Object is already initialized
  } else if (
    isObjectProperty(property) &&
    (value === undefined || value === null)
  ) {
    value = {}
  } else if (isArrayProperty(property) && !Array.isArray(value)) {
    value = []
  }

  function getInfoDescription(property: SchemaModelProperty): string {
    if (isGenericObject(property)) {
      return "This property is a JSON Object, which allows any arbitrary properties. You must fill in the text area with a valid JSON object."
    } else if (isObjectProperty(property)) {
      return "This property is a JSON Object, which requires specific properties (see below)."
    } else if (isGenericArray(property)) {
      return "JSON Array (supports any item types)"
    }
    return ""
  }
</script>

{#if (isObjectProperty(property) && !isGenericObject(property)) || (isArrayProperty(property) && !isGenericArray(property))}
  <div>
    <FormElement
      id={id + "_" + property.id}
      label={property.title}
      inputType="header_only"
      description={property.description}
      info_msg={describe_type(property)}
      info_description={getInfoDescription(property)}
      value=""
    />
    <div class="flex flex-col gap-6 py-4 mt-2 ml-4 border-l pl-6">
      {#if isObjectProperty(property) && !isGenericObject(property)}
        {#each getNestedSchemaForObject(property) as nestedProp}
          <RunInputFormElement
            property={nestedProp}
            bind:value={nestedValues[nestedProp.id]}
            {onInputChange}
            level={level + 1}
            path={`${path}.${nestedProp.id}`}
            {fullSchema}
          />
        {/each}
      {:else if isArrayProperty(property) && !isGenericArray(property)}
        <FormList
          bind:content={arrayContent}
          content_label={property.title + " Item"}
          start_with_one={false}
          empty_content={getArrayEmptyContent()}
        >
          <div slot="default" let:item_index>
            <textarea
              id={id + "_array_item_" + item_index}
              class="textarea textarea-bordered w-full"
              placeholder="Enter item value"
              bind:value={arrayContent[item_index]}
            />
          </div>
        </FormList>
      {/if}
    </div>
  </div>
{:else}
  <FormElement
    id={id + "_" + property.id}
    label={property.title}
    inputType={get_input_type(property)}
    height={getHeight(property)}
    description={getDescription(property)}
    optional={!property.required}
    value={isGenericObject(property) || isGenericArray(property) ? "" : value}
    info_msg={describe_type(property)}
    info_description={getInfoDescription(property)}
    on:input={handleInput}
  />
{/if}
