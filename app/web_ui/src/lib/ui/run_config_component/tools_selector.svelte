<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { available_tools, load_available_tools } from "$lib/stores"
  import { onMount } from "svelte"
  import type { ToolSetApiDescription, ToolSetType } from "$lib/types"
  import { tools_store, tools_store_initialized } from "$lib/stores/tools_store"
  import { goto } from "$app/navigation"

  export let project_id: string
  export let task_id: string | null = null
  export let tools: string[] = []
  export let hide_create_kiln_task_tool_button: boolean = false
  export let single_select: boolean = false
  export let single_select_selected_tool: string | null = null // Only used if single_select is true

  let tools_store_loaded_task_id: string | null = null
  onMount(async () => {
    await load_tools(project_id, task_id)
  })

  // Load tools if project_id or task_id changes
  $: load_tools(project_id, task_id)

  async function load_tools(project_id: string, task_id: string | null) {
    // Load available tools
    load_available_tools(project_id)

    if (!task_id) {
      tools = []
      tools_store_loaded_task_id = null
      return
    } else if (task_id !== tools_store_loaded_task_id) {
      // load selected tools for this task from tools_store
      await tools_store_initialized
      tools = $tools_store.selected_tool_ids_by_task_id[task_id] || []
      tools_store_loaded_task_id = task_id
    }
  }

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

  $: filter_unavailable_tools($available_tools[project_id], tools)

  // Filter out tools that are not in the available tools (server offline, tool removed, etc)
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

  const tool_set_order: ToolSetType[] = ["search", "kiln_task", "mcp", "demo"]

  function get_tool_options(
    available_tool_sets: ToolSetApiDescription[] | undefined,
  ): OptionGroup[] {
    if (!available_tool_sets || available_tool_sets.length === 0) {
      // When there are no available tools, we'll show the empty state "Add tools" button
      return []
    }

    let option_groups: OptionGroup[] = []

    tool_set_order.forEach((tool_set_type) => {
      let action_label: string | undefined = undefined
      let action_handler: (() => void) | undefined = undefined

      const add_create_kiln_task_tool_action =
        tool_set_type === "kiln_task" && !hide_create_kiln_task_tool_button
      if (add_create_kiln_task_tool_action) {
        action_label = "Create New"
        action_handler = () => {
          goto(`/settings/manage_tools/${project_id}/add_tools/kiln_task`)
        }
      }

      const tool_sets = available_tool_sets.filter(
        (tool_set) =>
          tool_set.type === tool_set_type && tool_set.tools.length > 0,
      )

      if (tool_sets.length > 0) {
        for (const tool_set of tool_sets) {
          let tools = tool_set.tools

          let options = tools.map((tool) => ({
            value: tool.id,
            label: tool.name,
            description: tool.description ? tool.description.trim() : undefined,
          }))

          option_groups.push({
            label: tool_set.set_name,
            options,
            action_label,
            action_handler,
          })
        }
      } else if (add_create_kiln_task_tool_action) {
        // Manually add the kiln_task option group when there are no kiln task tools
        // For discoverability since we want to show the "Create New" button
        option_groups.push({
          label: "Kiln Tasks as Tools",
          options: [],
          action_label,
          action_handler,
        })
      }
    })
    return option_groups
  }
</script>

<div>
  {#if single_select}
    <FormElement
      id="tools"
      label="Tools & Search"
      inputType="fancy_select"
      info_description="Select the tools available to the model. The model may or may not choose to use them."
      bind:value={single_select_selected_tool}
      fancy_select_options={get_tool_options($available_tools[project_id])}
      empty_state_message={$available_tools[project_id] === undefined
        ? "Loading tools..."
        : "No Tools Available"}
      empty_state_subtitle="Add Tools"
      empty_state_link={`/settings/manage_tools/${project_id}/add_tools`}
    />
  {:else}
    <FormElement
      id="tools"
      label="Tools & Search"
      inputType="multi_select"
      info_description="Select the tools available to the model. The model may or may not choose to use them."
      bind:value={tools}
      fancy_select_options={get_tool_options($available_tools[project_id])}
      empty_state_message={$available_tools[project_id] === undefined
        ? "Loading tools..."
        : "No Tools Available"}
      empty_state_subtitle="Add Tools"
      empty_state_link={`/settings/manage_tools/${project_id}/add_tools`}
    />
  {/if}
</div>
