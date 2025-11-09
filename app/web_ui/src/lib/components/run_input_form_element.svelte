<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import RunInputFormElement from "./run_input_form_element.svelte"
  import RunInputFormElementRefCapture from "./run_input_form_element_ref_capture.svelte"
  import { type SchemaModelProperty } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    MissingRequiredPropertyError,
    IncompleteObjectError,
  } from "$lib/utils/missing_required_property_error"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import RunInputArrayElement from "./run_input_array_element.svelte"

  export let property: SchemaModelProperty
  let value: string = ""
  export let onInputChange: (() => void) | null = null
  export let level: number = 0
  export let path: string = ""
  export let hideHeaderAndIndent: boolean = false
  export let parentOptional: boolean = false

  // Trigger onInputChange when value changes
  $: void (value, onInputChange?.())

  let id = "nested_input_" + Math.random().toString(36).substring(2, 15)

  let nestedComponents: Record<string, RunInputFormElement> = {}
  let arrayComponent: RunInputArrayElement | null = null

  function describe_type(property: SchemaModelProperty): string {
    let base_description = ""
    if (property.type === "string") {
      base_description = "String"
    } else if (property.type === "number") {
      base_description = "Number"
    } else if (property.type === "integer") {
      base_description = "Integer"
    } else if (property.type === "boolean") {
      base_description = "Boolean"
    } else if (property.type === "array") {
      base_description = "Array"
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
  ): "textarea" | "input" | "input_number" | "fancy_select" {
    if (isGenericObject(property)) {
      return "textarea"
    } else if (property.type === "boolean" || property.enum) {
      return "fancy_select"
    } else if (property.type === "string") {
      return "textarea"
    } else if (property.type === "number" || property.type === "integer") {
      return "input_number"
    }
    return "input"
  }

  function get_select_options(
    property: SchemaModelProperty,
  ): OptionGroup[] | undefined {
    if (property.type === "boolean") {
      return [
        {
          options: [
            {
              label: "True",
              value: "true",
            },
            {
              label: "False",
              value: "false",
            },
            {
              label: "Not Set",
              value: undefined,
            },
          ],
        },
      ]
    }
    if (property.enum) {
      return [
        {
          options: [
            ...property.enum.map((value) => ({
              label: (value ?? "null").toString(),
              value: value,
            })),
            {
              label: "Not Set",
              value: undefined,
            },
          ],
        },
      ]
    }
    return undefined
  }

  function getHeight(property: SchemaModelProperty): "large" | undefined {
    if (isGenericObject(property)) {
      return "large"
    }
    return undefined
  }

  function isArrayProperty(prop: SchemaModelProperty): boolean {
    return prop.type === "array"
  }

  function isObjectProperty(prop: SchemaModelProperty): boolean {
    return prop.type === "object"
  }

  // JSON schema can just define an arbitrary object, without a strong type.
  // In this case we need to let the user use a text area to enter the JSON object.
  function isGenericObject(property: SchemaModelProperty): boolean {
    if (property.type !== "object") return false

    // from spec: additionalProperties is true by default if omitted, and can be a dictionary with allowed types.

    // However, we don't want to regress the UI to generic JSON input when we have nice types defined and they didn't explicitly set additionalProperties
    if (
      property.additionalProperties === undefined &&
      property.properties &&
      property.properties.length > 0
    ) {
      return false
    }

    // Follow the spec for other cases, coalescing to true if not specified
    return !!(property.additionalProperties ?? true)
  }

  // Export function to build the value for this property
  export function buildValue(): unknown | undefined {
    // Case: arrays
    if (arrayComponent) {
      return arrayComponent.buildArrayValue()
    }

    // Case: structured objects, iterate each nested component and build the value
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

    // Shared logic for all types using value
    if (
      (value === "" || value === undefined || value === null) &&
      !property.required
    ) {
      // Valid empty value
      return undefined
    }
    // Usually "", can be undefined (enums) or null (input type=number with non-number string)
    if (!value && property.required) {
      throw new MissingRequiredPropertyError(
        "Required property not set: " + path,
        path,
      )
    }

    // For generic objects (flexible JSON)
    if (isGenericObject(property)) {
      try {
        const parsed = JSON.parse(value)
        // js.... typeof null and [] is "object"!?
        if (
          typeof parsed !== "object" ||
          parsed === null ||
          Array.isArray(parsed)
        ) {
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

    throw new Error("Unknown property type: " + property.type + " at " + path)
  }

  function getInfoDescription(
    property: SchemaModelProperty,
  ): string | undefined {
    if (isGenericObject(property)) {
      return "This property is a JSON Object, which allows any arbitrary properties. You must fill in the text area with a valid JSON object (e.g. '{\"a\": 1}')."
    }
    return undefined
  }
</script>

{#if (isObjectProperty(property) && !isGenericObject(property)) || isArrayProperty(property)}
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
      {:else if isArrayProperty(property)}
        <RunInputArrayElement
          bind:this={arrayComponent}
          {property}
          {onInputChange}
          level={level + 1}
          {path}
          parentOptional={parentOptional || !property.required}
        />
      {/if}
    </div>
  </div>
{:else}
  <FormElement
    id={id + "_" + property.id}
    label={property.title}
    inputType={get_input_type(property)}
    height={getHeight(property)}
    description={property.description || "No description"}
    optional={!property.required || parentOptional}
    fancy_select_options={get_select_options(property)}
    bind:value
    info_msg={describe_type(property)}
    info_description={getInfoDescription(property)}
  />
{/if}
