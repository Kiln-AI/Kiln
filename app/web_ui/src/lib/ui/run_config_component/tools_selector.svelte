<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import { available_tools, load_available_tools } from "$lib/stores"
  import { onMount } from "svelte"
  import type { ToolSetApiDescription } from "$lib/types"
  import { tools_store, tools_store_initialized } from "$lib/stores/tools_store"
  import { goto } from "$app/navigation"

  export let project_id: string
  export let task_id: string
  export let tools: string[] = []
  export let hide_create_kiln_task_tool_button: boolean = false

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
    // Check if the special "Create Tool from Kiln Task" option was selected
    if (tools.includes("__add_new_kiln_task__")) {
      // Remove the special option from the tools array
      tools = tools.filter((tool) => tool !== "__add_new_kiln_task__")
      // Navigate to create Kiln Task Tool page
      goto(`/settings/manage_tools/${project_id}/add_tools/kiln_task`)
    } else {
      tools_store.update((state) => ({
        ...state,
        selected_tool_ids_by_task_id: {
          ...state.selected_tool_ids_by_task_id,
          [task_id]: tools,
        },
      }))
    }
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

  function get_tool_options(
    available_tools: ToolSetApiDescription[],
  ): OptionGroup[] {
    let option_groups: OptionGroup[] = []

    available_tools?.forEach((tool_set) => {
      let tools = tool_set.tools
      // Track if we have Kiln Tasks tools
      if (
        tool_set.set_name === "Kiln Tasks" &&
        tools.length == 0 &&
        !hide_create_kiln_task_tool_button
      ) {
        // Add "Create Tool from Kiln Task" button only if no Kiln Tasks tools exist
        option_groups.push({
          label: "Kiln Tasks",
          options: [
            {
              value: "__add_new_kiln_task__",
              label: "Create Tool from Kiln Task",
              description: "Create a tool from an existing Kiln task",
              badge: "+",
              badge_color: "primary",
            },
          ],
        })
      } else if (tools.length > 0) {
        let options: Option[] = tools.map((tool) => ({
          value: tool.id,
          label: tool.name,
          description: tool.description || undefined,
        }))
        option_groups.push({
          label: tool_set.set_name,
          options: options,
        })
      }
    })

    return option_groups
  }
</script>

<div>
  {#if $available_tools[project_id]?.length > 0}
    <FormElement
      id="tools"
      label="Tools & Search"
      inputType="multi_select"
      info_description="Select the tools available to the model.\nThe model may or may not choose to use them."
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
