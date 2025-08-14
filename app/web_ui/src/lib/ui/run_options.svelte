<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { StructuredOutputMode } from "$lib/types"
  import { structuredOutputModeToString } from "$lib/utils/formatters"
  import { available_tools, load_available_tools } from "$lib/stores"
  import { onMount } from "svelte"
  import type { ToolApiDescription } from "$lib/types"

  // These defaults are used by every provider I checked (OpenRouter, Fireworks, Together, etc)
  export let temperature: number = 1.0
  export let top_p: number = 1.0
  export let structured_output_mode: StructuredOutputMode = "default"
  export let has_structured_output: boolean = false
  export let tools: string[] = []
  export let project_id: string

  onMount(async () => {
    load_tools(project_id)
  })

  function load_tools(project_id: string) {
    if (project_id) {
      load_available_tools(project_id)
    }
  }
  // Update if project_id changes
  $: load_tools(project_id)

  export let validate_temperature: (value: unknown) => string | null = (
    value: unknown,
  ) => {
    return validator(value, 0, 2, "Temperature")
  }

  export let validate_top_p: (value: unknown) => string | null = (
    value: unknown,
  ) => {
    return validator(value, 0, 1, "Top P")
  }

  export let validator: (
    value: unknown,
    min: number,
    max: number,
    name: string,
  ) => string | null = (
    value: unknown,
    min: number,
    max: number,
    name: string,
  ) => {
    // Handle string values by attempting conversion
    let numValue: number

    if (typeof value === "string") {
      if (value.trim() === "") {
        return "Value is required"
      }
      numValue = parseFloat(value)
      if (isNaN(numValue)) {
        return "Please enter a valid number"
      }
    } else if (typeof value === "number") {
      numValue = value
    } else {
      return "Please enter a valid number"
    }

    if (numValue < min) {
      return `${name} must be at least ${min}`
    }
    if (numValue > max) {
      return `${name} must be at most ${max}`
    }

    return null
  }

  const structured_output_options: OptionGroup[] = [
    {
      label: "Structured Output Mode",
      options: [
        {
          value: "json_schema",
          label: structuredOutputModeToString("json_schema") ?? "N/A",
          description:
            "Require the provider to provide the exact JSON schema expected.",
        },
        {
          value: "function_calling",
          label: structuredOutputModeToString("function_calling") ?? "N/A",
          description:
            "Request structured output using function calling with strict validation.",
        },
        {
          value: "function_calling_weak",
          label: structuredOutputModeToString("function_calling_weak") ?? "N/A",
          description:
            "Request structured output using function calling, without strict validation.",
        },
        {
          value: "json_mode",
          label: structuredOutputModeToString("json_mode") ?? "N/A",
          description:
            "Require the model return JSON, but without specifying the schema.",
        },
        {
          value: "json_instructions",
          label: structuredOutputModeToString("json_instructions") ?? "N/A",
          description:
            "Kiln will add instructions to the prompt requesting JSON matching your output schema.",
        },
        {
          value: "json_instruction_and_object",
          label:
            structuredOutputModeToString("json_instruction_and_object") ??
            "N/A",
          description: "Combine JSON instructions and JSON mode.",
        },
        {
          value: "json_custom_instructions",
          label:
            structuredOutputModeToString("json_custom_instructions") ??
            "Unknown",
          description:
            "Kiln will not add any instructions on how to structure the output. Your prompt should include custom instructions.",
        },
      ],
    },
  ]

  function get_tool_options(
    available_tools: ToolApiDescription[],
  ): OptionGroup[] {
    return [
      {
        options: available_tools?.map((tool) => ({
          value: tool.name,
          label: tool.name,
          description: tool.description || undefined,
        })),
      },
    ]
  }
</script>

<div>
  {#if $available_tools[project_id]?.length > 0}
    <FormElement
      id="tools"
      label="Tools"
      inputType="multi_select"
      info_description="Select the tools available to the model. The model may or may not choose to use them."
      bind:value={tools}
      fancy_select_options={get_tool_options($available_tools[project_id])}
    />
  {/if}

  <FormElement
    id="temperature"
    label="Temperature"
    inputType="input"
    info_description="A value from 0.0 to 2.0. Temperature is a parameter that controls the randomness of the model's output. Lower values make the output more focused and deterministic, while higher values make it more creative and varied."
    bind:value={temperature}
    validator={validate_temperature}
  />

  <FormElement
    id="top_p"
    label="Top P"
    inputType="input"
    info_description="A value from 0.0 to 1.0. Top P is a parameter that controls the diversity of the model's output. Lower values make the output more focused and deterministic, while higher values make it more creative and varied."
    bind:value={top_p}
    validator={validate_top_p}
  />

  {#if has_structured_output}
    <FormElement
      id="structured_output_mode"
      label="Structured Output"
      inputType="fancy_select"
      bind:value={structured_output_mode}
      fancy_select_options={structured_output_options}
      info_description="Choose how the model should return structured data. Defaults to a safe choice. Not all models/providers support all options so changing this may result in errors."
    />
  {/if}
</div>
