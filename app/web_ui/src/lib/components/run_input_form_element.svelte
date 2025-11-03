<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import RunInputFormElement from "./run_input_form_element.svelte"
  import RunInputFormElementRefCapture from "./run_input_form_element_ref_capture.svelte"
  import { type SchemaModelProperty } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    MissingRequiredPropertyError,
    IncompleteObjectError,
  } from "$lib/utils/missing_required_property_error"

  export let property: SchemaModelProperty
  let value: string = ""
  export let onInputChange: (() => void) | null = null
  export let level: number = 0
  export let path: string = ""
  export let hideHeaderAndIndent: boolean = false
  export let parentOptional: boolean = false

  let id = "nested_input_" + Math.random().toString(36).substring(2, 15)

  let nestedComponents: Record<string, RunInputFormElement> = {}

  let arrayContent: unknown[] = []

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
        base_description = "JSON Array"
      } else {
        base_description = "Array"
      }
    } else if (property.type === "object") {
      if (isGenericObject(property)) {
        base_description = "JSON Object"
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
    return property.description ?? "No description"
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
    if (!property.items) return false
    // TODO work on arrays. Is there no such thing as generic arrays? That would be ideal. Just objects in arrays.
    if (property.items.type === "object") {
      // Arrays of object are generic if the sub-object allows arbitrary properties
      return (property.items.additionalProperties ?? true) === true
    }
    // TODO likely wrong
    if (property.items.type === "array") {
      return true
    }
    return false
  }

  // JSON schema can just define an arbitrary object, without a strong type.
  // In this case we need to let the user use a text area to enter the JSON object.
  function isGenericObject(property: SchemaModelProperty): boolean {
    if (property.type !== "object") return false
    if (property.additionalProperties === true) return true
    return false
  }

  function getArrayEmptyContent(): unknown {
    return ""
  }

  // Export function to build the value for this property
  export function buildValue(): unknown | undefined {
    // For structured objects, iterate each nested component and build the value
    if (isObjectProperty(property) && !isGenericObject(property)) {
      const cleanedValue: Record<string, unknown> = {}
      let hasContent = false
      let missingRequiredContentError: MissingRequiredPropertyError | null =
        null

      for (const [id, nestedComponent] of Object.entries(nestedComponents)) {
        let nestedValue: unknown | undefined = undefined
        try {
          nestedValue = nestedComponent.buildValue()
        } catch (error) {
          if (error instanceof MissingRequiredPropertyError) {
            // This may be valid. If an object above this in the hierarchy is optional.
            missingRequiredContentError = error
            nestedValue = undefined
          } else {
            throw error
          }
        }
        if (nestedValue !== undefined) {
          cleanedValue[id] = nestedValue
          hasContent = true
        }
      }

      // Valid empty value: zero sub properties specified, but this is optional
      if (!property.required && !hasContent) {
        return undefined
      }
      // Check if we're missing required content, while having some other content.
      // If none are defined that might be okay (a parent is optional), but partial excluding required is always invalid.
      if (missingRequiredContentError && hasContent) {
        const source_path = missingRequiredContentError.source_path
        let additional_description = ""
        if (parentOptional || !property.required) {
          additional_description =
            "A parent of this property is optional, but you've defined some sub-fields while leaving a required sub-field empty. Etiher make all sub-fields blank or fill in the required sub-field."
        }
        throw new IncompleteObjectError(
          "Missing required property. " +
            additional_description +
            " Location: " +
            source_path,
          source_path,
        )
      }
      // Check if we're missing required content and this object isn't optional: always an error
      // Note, a parent optional object might still catch and recover this.
      if (missingRequiredContentError && property.required) {
        throw missingRequiredContentError
      }

      return cleanedValue
    }

    // For primitive types using value

    // Shared logic for all types using value
    if (value === "" && !property.required) {
      // Valid empty value
      return undefined
    }
    if (value === "" && property.required) {
      throw new MissingRequiredPropertyError(
        "Required property not set: " + path,
        path,
      )
    }

    if (property.type === "string") {
      // technically "" is a valid string, but let's be strict
      if (value === "" && property.required) {
        throw new MissingRequiredPropertyError(
          "Required property not set: " + path,
          path,
        )
      }
      return value
    }
    if (property.type === "boolean") {
      if (value !== "true" && value !== "false") {
        throw new Error("Boolean property must be 'true' or 'false': " + path)
      }
      return value === "true"
    }
    if (property.type === "number" || property.type === "integer") {
      // Form treats invalid numbers in form as null, so we handle here
      if (value === "" || value === null || value === undefined) {
        throw new MissingRequiredPropertyError(
          "Required property not set: " + path,
          path,
        )
      }
      const num = Number(value)
      if (isNaN(num)) {
        throw new Error("Property must be a number: " + path)
      }
      if (property.type === "integer" && !Number.isInteger(num)) {
        throw new Error("Property must be an integer: " + path)
      }
      return num
    }

    // For generic objects (flexible JSON)
    if (isGenericObject(property)) {
      try {
        const parsed = JSON.parse(value)
        if (typeof parsed !== "object") {
          throw new Error(
            "Property must be a JSON object string ('{...}'): " + path,
          )
        }
        return parsed
      } catch {
        throw new Error(
          "Property must be a valid JSON object string ('{...}'): " + path,
        )
      }
    }

    // For generic arrays (flexible JSON)
    if (isGenericArray(property)) {
      try {
        const parsed = JSON.parse(value)
        if (!Array.isArray(parsed)) {
          throw new Error(
            "Property must be a JSON array string ('[...]'): " + path,
          )
        }
        return parsed
      } catch {
        throw new Error(
          "Property must be a valid JSON array string ('[...]'): " + path,
        )
      }
    }

    // For structured arrays
    if (isArrayProperty(property) && !isGenericArray(property)) {
      /*if (!Array.isArray(value)) {
        return property.required ? [] : undefined
      }

      const cleanedArray: unknown[] = []
      let hasValidItems = false

      value.forEach((item, index) => {
        // For simple string items in structured arrays
        if (typeof item === "string") {
          if (item.trim() !== "") {
            cleanedArray.push(item)
            hasValidItems = true
          }
        } else if (typeof item === "object" && item !== null) {
          // For object items in structured arrays - check if they have content
          if (!isObjectEmpty(item)) {
            cleanedArray.push(item)
            hasValidItems = true
          }
        } else if (item !== undefined && item !== null) {
          cleanedArray.push(item)
          hasValidItems = true
        }
      })

      return hasValidItems ? cleanedArray : property.required ? [] : undefined
    }*/
      return undefined
    }

    return undefined
  }

  /*function cleanNestedValue(
    nestedProp: SchemaModelProperty,
    nestedValue: unknown,
  ): unknown | undefined {
    if (nestedValue === undefined || nestedValue === null) {
      return undefined
    }

    // Handle primitive types
    if (
      nestedProp.type === "string" ||
      nestedProp.type === "number" ||
      nestedProp.type === "integer" ||
      nestedProp.type === "boolean"
    ) {
      if (
        nestedValue === "" ||
        nestedValue === null ||
        nestedValue === undefined
      ) {
        return nestedProp.required
          ? nestedProp.type === "string"
            ? ""
            : nestedProp.type === "boolean"
              ? false
              : 0
          : undefined
      }
      return nestedValue
    }

    // Handle object types recursively
    if (nestedProp.type === "object") {
      if (
        typeof nestedValue === "object" &&
        nestedValue !== null &&
        !Array.isArray(nestedValue)
      ) {
        if (isObjectEmpty(nestedValue)) {
          return nestedProp.required ? {} : undefined
        }

        // If it's a generic object, return as-is
        if (isGenericObject(nestedProp)) {
          return nestedValue
        }

        // For structured objects, recursively clean nested properties
        const nestedProperties = getNestedSchemaForObject(nestedProp)
        const cleanedNestedValue: Record<string, unknown> = {}
        let hasContent = false

        nestedProperties.forEach((subProp) => {
          const subValue = (nestedValue as Record<string, unknown>)[subProp.id]
          const cleanedSubValue = cleanNestedValue(subProp, subValue)
          if (cleanedSubValue !== undefined) {
            cleanedNestedValue[subProp.id] = cleanedSubValue
            hasContent = true
          }
        })

        return hasContent
          ? cleanedNestedValue
          : nestedProp.required
            ? {}
            : undefined
      }
      return nestedProp.required ? {} : undefined
    }

    // Handle array types
    if (nestedProp.type === "array") {
      if (Array.isArray(nestedValue)) {
        if (isArrayEmpty(nestedValue)) {
          return nestedProp.required ? [] : undefined
        }

        const cleanedArray: unknown[] = []
        let hasValidItems = false

        nestedValue.forEach((item) => {
          if (typeof item === "string" && item.trim() !== "") {
            cleanedArray.push(item)
            hasValidItems = true
          } else if (
            typeof item === "object" &&
            item !== null &&
            !isObjectEmpty(item)
          ) {
            cleanedArray.push(item)
            hasValidItems = true
          } else if (item !== undefined && item !== null) {
            cleanedArray.push(item)
            hasValidItems = true
          }
        })

        return hasValidItems
          ? cleanedArray
          : nestedProp.required
            ? []
            : undefined
      }
      return nestedProp.required ? [] : undefined
    }

    return nestedValue
  }

  function isObjectEmpty(obj: unknown): boolean {
    if (!obj || typeof obj !== "object") return true
    if (Array.isArray(obj)) return false // it's an array, not an object
    return Object.keys(obj as Record<string, unknown>).length === 0
  }*/

  /*function isArrayEmpty(arr: unknown[]): boolean {
    if (!Array.isArray(arr)) return true
    if (arr.length === 0) return true
    if (arr.length === 1) {
      const item = arr[0]
      if (typeof item === "object" && item !== null) {
        return isObjectEmpty(item)
      } else if (typeof item === "string") {
        return item.trim() === ""
      }
    }
    return false
  }*/

  function getInfoDescription(property: SchemaModelProperty): string {
    if (isGenericObject(property)) {
      return "This property is a JSON Object, which allows any arbitrary properties. You must fill in the text area with a valid JSON object (e.g. '{...}')."
    } else if (isGenericArray(property)) {
      return "JSON Array (supports any item types)"
    }
    return ""
  }
</script>

{#if (isObjectProperty(property) && !isGenericObject(property)) || (isArrayProperty(property) && !isGenericArray(property))}
  <div>
    {#if !hideHeaderAndIndent}
      <FormElement
        id={id + "_" + property.id}
        label={property.title}
        inputType="header_only"
        description={property.description}
        info_msg={describe_type(property)}
        info_description={getInfoDescription(property)}
        value=""
      />
    {/if}
    <div
      class="flex flex-col gap-6 {hideHeaderAndIndent
        ? ''
        : 'py-4 mt-2 ml-4 border-l pl-6'}"
    >
      {#if isObjectProperty(property) && !isGenericObject(property)}
        {#each property.properties ?? [] as nestedProp}
          <RunInputFormElementRefCapture
            property={nestedProp}
            {onInputChange}
            level={level + 1}
            path={`${path}.${nestedProp.id}`}
            parentOptional={parentOptional || !property.required}
            on:ref={(e) => {
              // Workaround for svelte 4 to capture the ref
              const { inst } = e.detail
              if (inst instanceof RunInputFormElement) {
                nestedComponents[nestedProp.id] = inst
              }
            }}
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
    optional={!property.required || parentOptional}
    bind:value
    info_msg={describe_type(property)}
    info_description={getInfoDescription(property)}
    on:input={handleInput}
  />
{/if}
