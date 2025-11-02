<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import RunInputFormElement from "./run_input_form_element.svelte"
  import {
    model_from_schema_string,
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
      base_description = "Array of items"
    } else if (property.type === "object") {
      base_description = "Object with properties"
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
    if (property.type === "string") {
      return "textarea"
    } else if (property.type === "number" || property.type === "integer") {
      return "input_number"
    }
    return "input"
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

  function getNestedSchemaForArray(
    property: SchemaModelProperty,
  ): SchemaModelProperty[] {
    if (property.type !== "array") return []

    const jsonSchemaProperty = getNestedSchemaProperty(property)
    if (jsonSchemaProperty?.items) {
      if (Array.isArray(jsonSchemaProperty.items)) {
        // Handle tuple types
        return jsonSchemaProperty.items.map((item, index) => {
          const itemProp = item as JsonSchemaProperty
          return {
            id: index.toString(),
            title: itemProp.title || `Item ${index + 1}`,
            description: itemProp.description || "",
            type: itemProp.type,
            required: false,
          }
        })
      } else if ("type" in jsonSchemaProperty.items) {
        // Handle array with single item type
        const item = jsonSchemaProperty.items as JsonSchemaProperty
        return [
          {
            id: "item",
            title: item.title || "Item",
            description: item.description || "",
            type: item.type,
            required: false,
          },
        ]
      }
    }

    // Fallback - treat as string
    return [
      {
        id: "item",
        title: "Item",
        description: "Array item",
        type: "string",
        required: false,
      },
    ]
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

  function isObjectEmpty(obj: Record<string, unknown>): boolean {
    if (!obj || typeof obj !== "object") return true
    return Object.keys(obj).length === 0
  }

  function isArrayEmpty(arr: unknown[]): boolean {
    if (!Array.isArray(arr)) return true
    if (arr.length === 0) return true
    if (arr.length === 1) {
      const item = arr[0]
      if (typeof item === "object" && item !== null) {
        return isObjectEmpty(item as Record<string, unknown>)
      }
    }
    return false
  }

  function getArrayEmptyContent(): unknown {
    return ""
  }

  function handleGenericInput(e: Event) {
    const target = e.target as HTMLTextAreaElement
    if (target) {
      const newValue = target.value
      try {
        // Parse JSON to validate, but store as string
        JSON.parse(newValue)
        value = newValue
      } catch (error) {
        // Invalid JSON, still store the string value
        value = newValue
      }
    }
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
</script>

{#if isObjectProperty(property)}
  {#if isGenericObject(property)}
    <!-- Generic object - allow JSON input -->
    <FormElement
      id={id + "_" + property.id}
      label={property.title}
      inputType="textarea"
      height="large"
      description={property.description +
        " (JSON Object with flexible properties)"}
      optional={!property.required}
      value=""
      info_msg="JSON Object (supports any properties)"
      on:input={handleGenericInput}
    />
  {:else}
    <!-- Typed object - render nested fields -->
    <div class="mb-4">
      <FormElement
        id={id + "_" + property.id}
        label={property.title}
        inputType="header_only"
        description={property.description}
        info_msg={describe_type(property)}
        value=""
      />
      <div class="nested-content border-l-2 border-gray-500 pl-8">
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
      </div>
    </div>
  {/if}
{:else if isArrayProperty(property)}
  {#if isGenericArray(property)}
    <!-- Generic array - allow JSON input -->
    <FormElement
      id={id + "_" + property.id}
      label={property.title}
      inputType="textarea"
      height="large"
      description={property.description +
        " (JSON Array with flexible item types)"}
      optional={!property.required}
      value=""
      info_msg="JSON Array (supports any item types)"
      on:input={handleGenericInput}
    />
  {:else}
    <!-- Typed array - render FormList -->
    <div class="nested-container">
      <FormElement
        id={id + "_" + property.id}
        label={property.title}
        inputType="header_only"
        description={property.description}
        info_msg={describe_type(property)}
        value=""
      />
      <div class="nested-content border-l-2 border-gray-500 pl-8">
        <FormList
          bind:content={arrayContent}
          content_label={property.title + " Item"}
          start_with_one={false}
          empty_content={getArrayEmptyContent()}
        >
          <div slot="default" let:item let:item_index>
            <textarea
              id={id + "_array_item_" + item_index}
              class="textarea textarea-bordered w-full"
              placeholder="Enter item value"
              bind:value={arrayContent[item_index]}
            />
          </div>
        </FormList>
      </div>
    </div>
  {/if}
{:else}
  <div class="simple-property-container">
    <FormElement
      id={id + "_" + property.id}
      label={property.title}
      inputType={get_input_type(property)}
      description={property.description}
      optional={!property.required}
      bind:value
      info_msg={describe_type(property)}
    />
  </div>
{/if}

<style>
  .nested-container {
    margin-bottom: 1rem;
  }

  .nested-content {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding-top: 0.5rem;
    margin-left: 1rem;
  }

  .simple-property-container {
    margin-bottom: 0.75rem;
  }
</style>
