<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import type { ActionButton } from "$lib/types"
  import Run from "../../../../../run/run.svelte"
  import Output from "$lib/ui/output.svelte"
  import {
    current_task,
    model_name,
    model_info,
    load_model_info,
    prompt_name_from_id,
    current_task_prompts,
    provider_name_from_id,
    load_available_models,
    load_available_tools,
    available_tools,
  } from "$lib/stores"
  import { page } from "$app/stores"
  import { onMount, getContext } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun, StructuredOutputMode } from "$lib/types"
  import { isMcpRunConfig } from "$lib/types"
  import {
    formatDate,
    structuredOutputModeToString,
  } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import { prompt_link } from "$lib/utils/link_builder"
  import type { ProviderModels, PromptResponse } from "$lib/types"
  import { isMacOS } from "$lib/utils/platform"
  import type { Writable } from "svelte/store"
  import {
    get_tools_property_info,
    get_tool_names_from_ids,
    get_tool_server_name,
  } from "$lib/stores/tools_store"

  $: run_id = $page.params.run_id!
  $: task_id = $page.params.task_id!
  $: project_id = $page.params.project_id!
  // @ts-expect-error list_page is not a property of PageState
  $: list_page = ($page.state.list_page || []) as string[]

  // We should remove task_id from the URL, or load it by ID. $current_task is a lie
  let run: TaskRun | null = null
  let loading = true
  let load_error: KilnError | null = null
  let see_all_properties = false
  let tools_property_value: string | string[] = "Loading..."
  let tool_links: (string | null)[] | undefined

  $: {
    const run_config = run?.output?.source?.run_config
    let tool_ids: string[] = []
    if (!run_config) {
      tool_ids = []
    } else {
      const run_config_type = run_config.type
      switch (run_config_type) {
        case "mcp":
          tool_ids = []
          break
        case "kiln_agent":
          tool_ids = run_config.tools_config?.tools ?? []
          break
        default: {
          const _exhaustive: never = run_config_type
          throw new Error(`Unknown run config type: ${_exhaustive}`)
        }
      }
    }
    const tools_property_info = get_tools_property_info(
      tool_ids,
      project_id,
      $available_tools,
    )
    tools_property_value = tools_property_info.value
    tool_links = tools_property_info.links
  }

  function get_kiln_agent_properties(
    run: TaskRun | null,
    current_task_prompts: PromptResponse | null,
    model_info: ProviderModels | null,
  ): UiProperty[] {
    const properties: UiProperty[] = []
    const model_id = run?.output?.source?.properties?.model_name
    if (model_id && typeof model_id === "string") {
      properties.push({
        name: "Output Model",
        value: model_name(model_id, model_info),
      })
    }

    // Prompt ID previously was stored in the prompt_builder_name field
    let prompt_id = (
      run?.output?.source?.properties?.prompt_id ||
      run?.output?.source?.properties?.prompt_builder_name ||
      ""
    ).toString()
    if (prompt_id) {
      const prompt_name = prompt_name_from_id(prompt_id, current_task_prompts)
      if (prompt_name) {
        let link = prompt_link(project_id, task_id, prompt_id)
        properties.push({
          name: "Prompt",
          value: prompt_name,
          link: link,
        })
      }
    }

    properties.push({
      name: "Available Tools",
      value: tools_property_value,
      links: tool_links,
      badge: Array.isArray(tools_property_value) ? true : false,
    })
    return properties
  }

  function get_mcp_properties(run: TaskRun | null): UiProperty[] {
    const run_config = run?.output?.source?.run_config
    const tool_id =
      (isMcpRunConfig(run_config)
        ? run_config.tool_reference?.tool_id
        : null) || run?.output?.source?.properties?.tool_id

    const tool_name =
      typeof tool_id === "string"
        ? get_tool_names_from_ids(
            [tool_id],
            $available_tools[project_id] || [],
          )[0]
        : null
    const tool_server_name =
      typeof tool_id === "string"
        ? get_tool_server_name($available_tools, project_id, tool_id)
        : null

    const properties: UiProperty[] = [
      {
        name: "MCP Tool",
        value: tool_name || "Unknown",
      },
    ]

    if (tool_server_name) {
      properties.push({
        name: "Tool Server",
        value: tool_server_name,
      })
    }

    return properties
  }

  function get_kiln_agent_advanced_properties(
    run: TaskRun | null,
  ): UiProperty[] {
    const properties: UiProperty[] = []
    if (run?.output?.source?.properties?.model_provider) {
      properties.push({
        name: "Model Provider",
        value: provider_name_from_id(
          String(run.output.source.properties.model_provider),
        ),
      })
    }

    if (run?.output?.source?.properties?.temperature !== undefined) {
      properties.push({
        name: "Temperature",
        value: run.output.source.properties.temperature,
      })
    }

    if (run?.output?.source?.properties?.top_p !== undefined) {
      properties.push({
        name: "Top P",
        value: run.output.source.properties.top_p,
      })
    }

    if (run?.output?.source?.properties?.structured_output_mode) {
      let mode = run.output.source.properties.structured_output_mode
      if (typeof mode === "string") {
        const json_mode = structuredOutputModeToString(
          mode as StructuredOutputMode,
        )
        if (json_mode) {
          properties.push({
            name: "JSON Mode",
            value: json_mode,
          })
        }
      }
    }
    return properties
  }

  function get_properties(
    run: TaskRun | null,
    current_task_prompts: PromptResponse | null,
    model_info: ProviderModels | null,
  ) {
    let properties: UiProperty[] = []
    const run_config = run?.output?.source?.run_config

    if (run?.id) {
      properties.push({
        name: "ID",
        value: run.id,
      })
    }

    if (run?.input_source?.type) {
      properties.push({
        name: "Input Source",
        value:
          run.input_source.type.charAt(0).toUpperCase() +
          run.input_source.type.slice(1),
      })
    }

    if (!run_config) {
      // if run_config is null, render the kiln agent properties
      properties.push(
        ...get_kiln_agent_properties(run, current_task_prompts, model_info),
      )
    } else {
      const run_config_type = run_config.type
      switch (run_config_type) {
        case "mcp": {
          properties.push(...get_mcp_properties(run))
          break
        }
        case "kiln_agent":
          // if run_config is kiln_agent, render the kiln agent properties
          properties.push(
            ...get_kiln_agent_properties(run, current_task_prompts, model_info),
          )
          break
        default: {
          const _exhaustive: never = run_config_type
          throw new Error(`Unknown run config type: ${_exhaustive}`)
        }
      }
    }

    if (run?.created_at) {
      properties.push({
        name: "Created At",
        value: formatDate(run.created_at),
      })
    }

    let topic_path: string | undefined = undefined
    if (
      run?.input_source?.properties?.topic_path &&
      typeof run?.input_source?.properties?.topic_path === "string"
    ) {
      topic_path = run?.input_source?.properties?.topic_path?.replaceAll(
        ">>>>>",
        " > ",
      )
    }
    if (topic_path) {
      properties.push({
        name: "Topic",
        value: topic_path,
      })
    }

    return properties
  }

  function get_advanced_properties(run: TaskRun | null) {
    let properties: UiProperty[] = []
    const run_config = run?.output?.source?.run_config
    if (!run_config) {
      properties.push(...get_kiln_agent_advanced_properties(run))
    } else {
      const run_config_type = run_config.type
      switch (run_config_type) {
        case "mcp":
          break
        case "kiln_agent": {
          properties.push(...get_kiln_agent_advanced_properties(run))
          break
        }
        default: {
          const _exhaustive: never = run_config_type
          throw new Error(`Unknown run config type: ${_exhaustive}`)
        }
      }
    }

    if (run?.input_source?.properties?.created_by) {
      properties.push({
        name: "Created By",
        value: run.input_source.properties.created_by,
      })
    }

    return properties
  }

  onMount(async () => {
    await Promise.all([
      load_run(),
      load_model_info(),
      load_available_models(),
      load_available_tools(project_id),
    ])
  })

  async function load_run() {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
        {
          params: {
            path: { project_id, task_id, run_id: run_id },
          },
        },
      )
      if (error) {
        throw error
      }
      run = data
    } catch (error) {
      if (error instanceof Error && error.message.includes("Load failed")) {
        load_error = new KilnError(
          "Could not load run. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        load_error = createKilnError(error)
      }
    } finally {
      loading = false
    }
  }

  let delete_dialog: DeleteDialog | null = null
  let deleted: Record<string, boolean> = {}
  $: delete_url = `/api/projects/${project_id}/tasks/${task_id}/runs/${run_id}`
  function after_delete() {
    deleted[run_id] = true
  }

  function next_run() {
    const index = list_page.indexOf(run_id)
    if (index < list_page.length - 1) {
      const next_run_id = list_page[index + 1]
      load_run_by_id(next_run_id)
    }
  }

  function prev_run() {
    const index = list_page.indexOf(run_id)
    if (index > 0) {
      const prev_run_id = list_page[index - 1]
      load_run_by_id(prev_run_id)
    }
  }

  function load_run_by_id(new_run_id: string) {
    load_error = null
    run_id = new_run_id
    run = null
    goto(`/dataset/${project_id}/${task_id}/${run_id}/run`, {
      state: { list_page: list_page },
    })
    load_run()
  }

  let buttons: ActionButton[] = []
  $: {
    buttons = []
    if (!deleted[run_id]) {
      buttons.push({
        icon: "/images/delete.svg",
        handler: () => delete_dialog?.show(),
        shortcut: isMacOS() ? "Backspace" : "Delete",
      })
    }
    if (list_page.length > 1) {
      const index = list_page.indexOf(run_id)
      if (index !== -1) {
        buttons.push({
          icon: "/images/previous.svg",
          handler: prev_run,
          shortcut: "ArrowLeft",
          disabled: index === 0,
        })
        buttons.push({
          icon: "/images/next.svg",
          handler: next_run,
          shortcut: "ArrowRight",
          disabled: index === list_page.length - 1,
        })
      }
    }
  }

  // Fancy logic to maintain the search string when navigating back to the dataset page (filters, sorting, etc.)
  const lastPageUrl = getContext<Writable<URL | undefined>>("lastPageUrl")
  function get_breadcrumbs() {
    if (!$lastPageUrl) {
      return []
    }

    try {
      const referrerPath = $lastPageUrl.pathname

      // Check if the referrer path is /dataset/{project_id}/{task_id}
      // since we only want to breadcrumb back to that page
      const expectedPath = `/dataset/${$page.params.project_id}/${$page.params.task_id}`

      if (referrerPath === expectedPath) {
        return [
          {
            label: "Dataset",
            // Include the full URL with search params to a
            href: $lastPageUrl.pathname + $lastPageUrl.search,
          },
        ]
      }
    } catch (error) {
      console.warn("Failed to parse referrer URL:", error)
    }

    return []
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Dataset Run"
    subtitle={run?.id ? `Run ID: ${run.id}` : undefined}
    action_buttons={buttons}
    breadcrumbs={get_breadcrumbs()}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if deleted[run_id] === true}
      <div class="badge badge-error badge-lg p-4">Run Deleted</div>
    {:else if load_error}
      <div class="text-error">{load_error.getMessage()}</div>
    {:else if run && $current_task}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
        <div class="grow">
          <div class="text-xl font-bold mb-4">Input</div>
          <Output raw_output={run.input} />
        </div>
        <div class="w-72 2xl:w-96 flex-none flex flex-col">
          <PropertyList
            properties={[
              ...get_properties(run, $current_task_prompts, $model_info),
              ...(see_all_properties ? get_advanced_properties(run) : []),
            ]}
            title="Properties"
          />
          <button
            class="text-xs text-gray-500 underline text-left cursor-pointer bg-transparent border-none p-0 mt-4"
            on:click={() => (see_all_properties = !see_all_properties)}
          >
            {see_all_properties ? "See Less" : "See All"}
          </button>
        </div>
      </div>
      <Run initial_run={run} task={$current_task} {project_id} />
    {:else}
      <div class="text-gray-500 text-lg">Run not found</div>
    {/if}
  </AppPage>
</div>

<DeleteDialog
  name="Dataset Run"
  bind:this={delete_dialog}
  {delete_url}
  {after_delete}
/>
