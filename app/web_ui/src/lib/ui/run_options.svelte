<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { StructuredOutputMode } from "$lib/types"
  import { structuredOutputModeToString } from "$lib/utils/formatters"
  import { available_tools, load_available_tools } from "$lib/stores"
  import { onMount } from "svelte"
  import type { ToolSetApiDescription } from "$lib/types"
  import { tools_store, tools_store_initialized } from "$lib/stores/tools_store"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  // These defaults are used by every provider I checked (OpenRouter, Fireworks, Together, etc)
  export let temperature: number = 1.0
  export let top_p: number = 1.0
  export let structured_output_mode: StructuredOutputMode = "default"
  export let has_structured_output: boolean = false
  export let project_id: string
  export let task_id: string
  export let tools: string[] = []
  export let read_only: boolean = false

  onMount(async () => {
    await load_tools(project_id, task_id)
  })

  let tools_store_loaded_task_id: string | null = null
  async function load_tools(project_id: string, task_id: string) {
    // Load available tools
    if (project_id) {
      load_available_tools(project_id)
    }

    // load selected tools for this task from tools_store
    if (task_id !== tools_store_loaded_task_id) {
      await tools_store_initialized
      tools = $tools_store.selected_tool_ids_by_task_id[task_id] || []
      tools_store_loaded_task_id = task_id
    }
  }
  // Load tools if project_id or task_id changes
  $: load_tools(project_id, task_id)

  // Update tools_store when tools changes, only after initial load so we don't update it with the empty initial value
  $: if (task_id && tools && tools_store_loaded_task_id === task_id) {
    tools_store.update((state) => ({
      ...state,
      selected_tool_ids_by_task_id: {
        ...state.selected_tool_ids_by_task_id,
        [task_id]: tools,
      },
    }))
  }

  // filter out tools that are not in the available tools (server offline, tool removed, etc)
  function filter_unavailable_tools(
    available_tools: ToolSetApiDescription[] | undefined,
    current_tools: string[],
  ) {
    if (
      !available_tools ||
      !project_id ||
      !tools_store_loaded_task_id ||
      !current_tools ||
      current_tools.length === 0
    ) {
      return
    }

    const available_tool_ids = new Set(
      available_tools.flatMap((tool_set) =>
        tool_set.tools.map((tool) => tool.id),
      ),
    )

    const unavailable_tools = tools.filter(
      (tool_id) => !available_tool_ids.has(tool_id),
    )

    if (unavailable_tools.length > 0) {
      console.warn("Removing unavailable tools:", unavailable_tools)
      tools = tools.filter((tool_id) => available_tool_ids.has(tool_id))
    }
  }
  $: filter_unavailable_tools($available_tools[project_id], tools)

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
    available_tools: ToolSetApiDescription[],
  ): OptionGroup[] {
    let option_groups: OptionGroup[] = []

    available_tools?.forEach((tool_set) => {
      option_groups.push({
        label: tool_set.set_name,
        options: tool_set.tools.map((tool) => ({
          value: tool.id,
          label: tool.name,
          description: tool.description || undefined,
        })),
      })
    })
    return option_groups
  }

  // Get display names for selected values
  $: selected_tools_names = get_selected_tools_names(
    tools,
    $available_tools[project_id],
  )
  $: selected_structured_output_name = structuredOutputModeToString(
    structured_output_mode,
  )

  function get_selected_tools_names(
    selected_tool_ids: string[],
    available_tools: ToolSetApiDescription[],
  ): string[] {
    if (!available_tools) return []
    return selected_tool_ids.map((id) => {
      for (const tool_set of available_tools) {
        const tool = tool_set.tools.find((t) => t.id === id)
        if (tool) return tool.name
      }
      return id
    })
  }
</script>

<div>
  {#if $available_tools[project_id]?.length > 0}
    {#if read_only}
      <FormElement
        id="tools_readonly"
        label="Tools"
        inputType="header_only"
        info_description="Select the tools available to the model. The model may or may not choose to use them."
      />
      <div class="relative">
        <div
          class="select select-bordered w-full flex items-center min-h-12 bg-base-200/50 text-base-content/70"
          style="background-image: none;"
        >
          <span class="truncate">
            {#if selected_tools_names.length > 0}
              {selected_tools_names.join(", ")}
            {:else}
              No tools selected
            {/if}
          </span>
        </div>
      </div>
    {:else}
      <FormElement
        id="tools"
        label="Tools"
        inputType="multi_select"
        info_description="Select the tools available to the model. The model may or may not choose to use them."
        bind:value={tools}
        fancy_select_options={get_tool_options($available_tools[project_id])}
      />
    {/if}
  {/if}

  {#if read_only}
    <FormElement
      id="temperature_readonly"
      label="Temperature"
      inputType="header_only"
      info_description="A value from 0.0 to 2.0. Temperature is a parameter that controls the randomness of the model's output. Lower values make the output more focused and deterministic, while higher values make it more creative and varied."
    />
    <div class="relative">
      <div
        class="select select-bordered w-full flex items-center bg-base-200/50 text-base-content/70"
        style="background-image: none;"
      >
        <span class="truncate">{temperature}</span>
      </div>
    </div>
  {:else}
    <FormElement
      id="temperature"
      label="Temperature"
      inputType="input"
      info_description="A value from 0.0 to 2.0. Temperature is a parameter that controls the randomness of the model's output. Lower values make the output more focused and deterministic, while higher values make it more creative and varied."
      bind:value={temperature}
      validator={validate_temperature}
    />
  {/if}

  {#if read_only}
    <FormElement
      id="top_p_readonly"
      label="Top P"
      inputType="header_only"
      info_description="A value from 0.0 to 1.0. Top P is a parameter that controls the diversity of the model's output. Lower values make the output more focused and deterministic, while higher values make it more creative and varied."
    />
    <div class="relative">
      <div
        class="select select-bordered w-full flex items-center bg-base-200/50 text-base-content/70"
        style="background-image: none;"
      >
        <span class="truncate">{top_p}</span>
      </div>
    </div>
  {:else}
    <FormElement
      id="top_p"
      label="Top P"
      inputType="input"
      info_description="A value from 0.0 to 1.0. Top P is a parameter that controls the diversity of the model's output. Lower values make the output more focused and deterministic, while higher values make it more creative and varied."
      bind:value={top_p}
      validator={validate_top_p}
    />
  {/if}

  {#if has_structured_output}
    {#if read_only}
      <FormElement
        id="structured_output_readonly"
        label="Structured Output"
        inputType="header_only"
        info_description="Choose how the model should return structured data. Defaults to a safe choice. Not all models/providers support all options so changing this may result in errors."
      />
      <div class="relative">
        <div
          class="select select-bordered w-full flex items-center bg-base-200/50 text-base-content/70"
          style="background-image: none;"
        >
          <span class="truncate">{selected_structured_output_name}</span>
        </div>
      </div>
    {:else}
      <FormElement
        id="structured_output_mode"
        label="Structured Output"
        inputType="fancy_select"
        bind:value={structured_output_mode}
        fancy_select_options={structured_output_options}
        info_description="Choose how the model should return structured data. Defaults to a safe choice. Not all models/providers support all options so changing this may result in errors."
      />
    {/if}
  {/if}
</div>
