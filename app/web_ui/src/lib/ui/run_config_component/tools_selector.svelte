<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { available_tools, load_available_tools } from "$lib/stores"
  import { onMount } from "svelte"
<<<<<<< HEAD
  import type {
    ToolApiDescription,
    ToolSetApiDescription,
    ToolSetType,
  } from "$lib/types"
  import {
    tools_store,
    tools_store_initialized,
    CODE_EVAL_ONLY_TOOL_IDS,
  } from "$lib/stores/tools_store"
=======
  import type { ToolSetApiDescription } from "$lib/types"
  import { tools_store, tools_store_initialized } from "$lib/stores/tools_store"
  import type { SandboxCodeContext } from "$lib/stores/tools_store"
>>>>>>> 721c4941b
  import { goto } from "$app/navigation"
  import type { ToolsSelectorSettings } from "./tools_selector_settings"
  import {
    build_tool_option_groups,
    selectable_tool_sets,
  } from "./tool_options"

  export let project_id: string
  export let task_id: string | null = null
  export let label: string = "Tools & Search"
  export let settings: Partial<ToolsSelectorSettings> = {}
  export let tools: string[] = []
  export let single_select_selected_tool: string | null = null // Only used if single_select is true
  export let pending_tool_id: string | null = null

  let tools_store_loaded_task_id: string | null = null

  let default_tools_selector_settings: ToolsSelectorSettings = {
    mandatory_tools: [],
    description: undefined,
    info_description:
      "Select the tools available to the model. The model may or may not choose to use them.",
    hide_info_description: false,
    hide_create_kiln_task_tool_button: false,
    disabled: false,
    empty_label: "None",
    single_select: false,
    optional: true,
<<<<<<< HEAD
    code_eval_context: false,
=======
    sandbox_code_context: "none",
>>>>>>> 721c4941b
  }
  $: tools_selector_settings = {
    ...default_tools_selector_settings,
    ...settings,
  }
  $: has_explicit_mandatory_tools = settings.mandatory_tools !== undefined

  onMount(async () => {
    await load_tools(project_id, task_id)
  })

  // Load tools if project_id or task_id changes
  $: load_tools(project_id, task_id)

  // When fine-tuning locks tools to an explicit empty set, clear any stale
  // persisted selections so the bound value matches the disabled UI state.
  $: if (
    tools_selector_settings.disabled &&
    has_explicit_mandatory_tools &&
    Array.isArray(tools_selector_settings.mandatory_tools) &&
    tools_selector_settings.mandatory_tools.length === 0 &&
    tools.length > 0
  ) {
    tools = []
  }

  // Every tool id this picker may hold in `tools`, given its context. The dropdown,
  // a pending ?tool_id= injection and anything already persisted all resolve through
  // this, so filtering the displayed options alone can never leave a context-forbidden
  // tool sitting in the bound value.
  function selectable_tool_ids(
    available_tool_sets: ToolSetApiDescription[] | undefined,
    sandbox_code_context: SandboxCodeContext,
  ): Set<string> {
    const ids = new Set<string>()
    for (const tool_set of selectable_tool_sets(
      available_tool_sets,
      sandbox_code_context,
    )) {
      for (const tool of tool_set.tools) {
        ids.add(tool.id)
      }
    }
    return ids
  }

  async function load_tools(project_id: string, task_id: string | null) {
    // Load available tools
    load_available_tools(project_id)

    if (!task_id) {
      // Clone so fancy_select's in-place push (selected_values.push) doesn't
      // mutate the shared mandatory_tools array and retroactively disable
      // the option the user just selected.
      tools = [...(tools_selector_settings.mandatory_tools || [])]
      tools_store_loaded_task_id = null
    } else if (task_id !== tools_store_loaded_task_id) {
      // load selected tools for this task from tools_store
      await tools_store_initialized
      const existing_tools =
        $tools_store.selected_tool_ids_by_task_id[task_id] || []

      // Combine mandatory tools with existing selected tools
      const combined_tools = [
        ...(tools_selector_settings.mandatory_tools || []),
        ...existing_tools,
      ]
      // Remove duplicates while preserving order (mandatory tools first)
      tools = [...new Set(combined_tools)]

      tools_store_loaded_task_id = task_id
    }

    apply_pending_tool()
  }

  function apply_pending_tool() {
    if (!pending_tool_id || tools.includes(pending_tool_id)) {
      return
    }
    // A ?tool_id= in the URL is untrusted input, so it earns a selection only if
    // this picker could have offered the tool itself.
    const selectable = selectable_tool_ids(
      $available_tools[project_id],
      tools_selector_settings.sandbox_code_context,
    )
    if (!selectable.has(pending_tool_id)) {
      return
    }
    tools = [...new Set([...tools, pending_tool_id])]
  }

  // If tools load after initial render, re-apply pending tool
  $: if (pending_tool_id && $available_tools[project_id]) {
    apply_pending_tool()
  }

  $: drop_unselectable_tools(
    $available_tools[project_id],
    tools,
    tools_selector_settings.sandbox_code_context,
  )

  // Update tools_store when tools changes, only after initial load so we don't
  // update it with the empty initial value. Ordered after drop_unselectable_tools
  // so a forbidden selection is never persisted, not even transiently.
  $: if (task_id && tools && tools_store_loaded_task_id === task_id) {
    tools_store.update((state) => ({
      ...state,
      selected_tool_ids_by_task_id: {
        ...state.selected_tool_ids_by_task_id,
        [task_id]: tools,
      },
    }))
  }

  // Drop anything this picker may not hold: tools the server no longer offers
  // (server offline, tool removed) and tools its sandboxed-code context forbids.
  // This is the write-path counterpart to the dropdown's filtering — without it a
  // selection that was persisted earlier, or injected via ?tool_id=, would survive
  // in `tools` and be saved back out.
  function drop_unselectable_tools(
    available_tool_sets: ToolSetApiDescription[] | undefined,
    current_tools: string[],
    sandbox_code_context: SandboxCodeContext,
  ) {
    if (
      !available_tool_sets ||
      !project_id ||
      !current_tools ||
      current_tools.length === 0
    ) {
      return
    }

    const selectable = selectable_tool_ids(
      available_tool_sets,
      sandbox_code_context,
    )

    const dropped = current_tools.filter((tool_id) => !selectable.has(tool_id))

    if (dropped.length > 0) {
      console.warn("Removing tools not selectable in this picker:", dropped)
      tools = current_tools.filter((tool_id) => selectable.has(tool_id))
    }
  }

<<<<<<< HEAD
  const tool_set_order: ToolSetType[] = [
    "builtin",
    "code",
    "search",
    "kiln_task",
    "mcp",
    "demo",
  ]

  // Show the function name alongside the description when it differs from the
  // display name. Multiple tools (code tools especially) can share a function
  // name while having distinct display names, so both are needed to tell them
  // apart. Also makes the function name searchable in the dropdown.
  function tool_option_description(
    tool: ToolApiDescription,
  ): string | undefined {
    const description = tool.description ? tool.description.trim() : undefined
    const function_name =
      tool.function_name && tool.function_name !== tool.name
        ? tool.function_name
        : undefined
    if (!function_name) {
      return description
    }
    return description ? `${function_name}\n${description}` : function_name
  }

  function get_tool_options(
    available_tool_sets: ToolSetApiDescription[] | undefined,
    code_eval_context: boolean,
=======
  function get_tool_options(
    available_tool_sets: ToolSetApiDescription[] | undefined,
    sandbox_code_context: SandboxCodeContext,
>>>>>>> 721c4941b
  ): OptionGroup[] {
    return build_tool_option_groups(available_tool_sets, {
      value_field: "id",
      sandbox_code_context,
      option_disabled: (tool) =>
        tools_selector_settings.mandatory_tools
          ? tools_selector_settings.mandatory_tools.includes(tool.id)
          : false,
      group_action: (tool_set_type) => {
        if (
          tool_set_type !== "kiln_task" ||
          tools_selector_settings.hide_create_kiln_task_tool_button
        ) {
          return undefined
        }
<<<<<<< HEAD
      }

      const tool_sets = available_tool_sets.filter(
        (tool_set) =>
          tool_set.type === tool_set_type && tool_set.tools.length > 0,
      )

      if (tool_sets.length > 0) {
        for (const tool_set of tool_sets) {
          let tools = tool_set.tools.filter(
            (tool) =>
              code_eval_context || !CODE_EVAL_ONLY_TOOL_IDS.includes(tool.id),
          )

          if (tools.length === 0) {
            continue
          }

          let options = tools.map((tool) => ({
            value: tool.id,
            label: tool.name,
            description: tool_option_description(tool),
            disabled: tools_selector_settings.mandatory_tools
              ? tools_selector_settings.mandatory_tools.includes(tool.id)
              : false,
          }))

          option_groups.push({
            label: tool_set.set_name,
            options,
            action_label,
            action_handler,
          })
=======
        return {
          action_label: "Create New",
          action_handler: () => {
            goto(`/tools/${project_id}/add_tools/kiln_task`)
          },
          // Keep the group when the project has no Kiln task tools yet, so the
          // "Create New" button stays discoverable.
          empty_group_label: "Kiln Tasks as Tools",
>>>>>>> 721c4941b
        }
      },
    })
  }

  $: common_props = {
    id: "tools",
    label,
    description: tools_selector_settings.description,
    info_description: tools_selector_settings.hide_info_description
      ? undefined
      : tools_selector_settings.info_description,
    fancy_select_options: get_tool_options(
      $available_tools[project_id],
<<<<<<< HEAD
      tools_selector_settings.code_eval_context,
=======
      tools_selector_settings.sandbox_code_context,
>>>>>>> 721c4941b
    ),
    empty_label:
      tools_selector_settings.empty_label ??
      default_tools_selector_settings.empty_label,
    empty_state_message:
      $available_tools[project_id] === undefined
        ? "Loading tools..."
        : "No Tools Available",
    empty_state_subtitle: "Add Tools",
    empty_state_link: `/tools/${project_id}/add_tools`,
    disabled: tools_selector_settings.disabled,
    optional: tools_selector_settings.optional,
  }
</script>

<div>
  {#if tools_selector_settings.single_select}
    <FormElement
      {...common_props}
      inputType="fancy_select"
      bind:value={single_select_selected_tool}
    />
  {:else}
    <FormElement
      {...common_props}
      inputType="multi_select"
      bind:value={tools}
    />
  {/if}
</div>
