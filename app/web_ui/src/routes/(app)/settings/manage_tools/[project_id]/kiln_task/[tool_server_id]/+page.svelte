<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type {
    ExternalToolServerApiDescription,
    Task,
    TaskRunConfig,
    KilnTaskServerProperties,
  } from "$lib/types"
  import {
    load_available_models,
    load_model_info,
    model_info,
    model_name,
    provider_name_from_id,
    available_tools,
    load_available_tools,
    get_task_composite_id,
  } from "$lib/stores"
  import Warning from "$lib/ui/warning.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"

  $: project_id = $page.params.project_id
  $: tool_server_id = $page.params.tool_server_id
  $: is_archived = tool_server
    ? (tool_server.properties as KilnTaskServerProperties).is_archived
    : false

  let task: Task | null = null
  let run_config: TaskRunConfig | null = null
  let tool_server: ExternalToolServerApiDescription | null = null
  let loading = true
  let loading_error: KilnError | null = null
  let archive_error: KilnError | null = null
  let unarchive_error: KilnError | null = null

  onMount(async () => {
    await fetch_tool_server()
    await load_available_models()
    await load_model_info()
    if (project_id) {
      await load_available_tools(project_id)
    }
  })

  // Use a separate reactive statement to trigger data loading when tool_server changes
  $: if (tool_server) {
    load_tool_server_data(tool_server)
  }

  async function load_tool_server_data(
    tool_server: ExternalToolServerApiDescription,
  ) {
    const properties = tool_server.properties as KilnTaskServerProperties
    const task_id = properties.task_id

    if (task_id) {
      // Load task data
      try {
        const fetched_task = await get_task(task_id)
        task = fetched_task
      } catch (err) {
        console.error("Failed to fetch task:", err)
      }

      // Load prompts for the task
      await load_task_prompts(project_id, task_id)

      // Load run configs and find the specific one
      const run_config_id = properties.run_config_id
      if (run_config_id) {
        try {
          await load_task_run_configs(project_id, task_id)
          const run_configs =
            $run_configs_by_task_composite_id[
              get_task_composite_id(project_id, task_id)
            ]
          run_config =
            run_configs?.find((rc) => rc.id === run_config_id) || null
        } catch (err) {
          console.error("Failed to load run configs:", err)
        }
      }
    }
  }

  async function get_task(task_id: string): Promise<Task> {
    if (!project_id || !task_id) {
      throw new Error("Project or task ID not set.")
    }
    const { data: task_response, error: get_error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}",
      {
        params: {
          path: {
            project_id,
            task_id,
          },
        },
      },
    )
    if (get_error) {
      throw get_error
    }
    if (!task_response) {
      throw new Error("No task data returned from API.")
    }
    return task_response
  }

  async function fetch_tool_server() {
    try {
      loading = true
      loading_error = null

      if (!project_id) {
        throw new Error("No project ID provided")
      }

      if (!tool_server_id) {
        throw new Error("No tool server ID provided")
      }

      // Fetch the specific tool by ID
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tool_servers/{tool_server_id}",
        {
          params: {
            path: {
              project_id,
              tool_server_id,
            },
          },
        },
      )

      if (error) {
        throw error
      }

      tool_server = data as ExternalToolServerApiDescription
    } catch (err) {
      loading_error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function go_back() {
    goto(`/settings/manage_tools/${project_id}`)
  }

  function clone_tool() {
    if (!tool_server) {
      return
    }

    // Navigate to the add tool page with pre-filled data
    const properties = tool_server.properties as KilnTaskServerProperties
    const params = new URLSearchParams({
      name: String(properties.name || ""),
      description: String(properties.description || ""),
      task_id: String(properties.task_id || ""),
      run_config_id: String(properties.run_config_id || ""),
    })

    goto(
      `/settings/manage_tools/${project_id}/add_tools/kiln_task?${params.toString()}`,
    )
  }

  function get_tool_names_from_ids(tool_ids: string[]): string[] {
    if (!project_id || !$available_tools[project_id]) {
      return tool_ids // Return IDs if we don't have the tools loaded
    }

    const all_tools = $available_tools[project_id].flatMap(
      (tool_set) => tool_set.tools,
    )
    const tool_map = new Map(all_tools.map((tool) => [tool.id, tool.name]))

    return tool_ids.map((id) => tool_map.get(id) || id) // Fall back to ID if name not found
  }

  function get_tool_properties(tool: ExternalToolServerApiDescription) {
    return [
      { name: "ID", value: tool.id || "N/A" },
      {
        name: "Tool Name",
        value: tool.name || "",
        tooltip: "The tool name the model sees and calls.",
      },
      {
        name: "Tool Description",
        value: tool.description || "",
        tooltip: "The tool description the model sees.",
      },
      {
        name: "Created At",
        value: formatDate(tool.created_at ?? undefined),
      },
      { name: "Created By", value: tool.created_by || "N/A" },
    ]
  }

  function get_task_properties(task: Task | null) {
    if (!task) {
      return [{ name: "Status", value: "Task Not Found", error: true }]
    }

    return [
      { name: "ID", value: task.id || "N/A" },
      { name: "Task Name", value: task.name || "N/A" },
    ]
  }

  function get_run_config_properties(run_config: TaskRunConfig | null) {
    if (!run_config || !$model_info) {
      return [{ name: "Status", value: "Run Config Not Found", error: true }]
    }

    return [
      {
        name: "ID",
        value: run_config.id || "N/A",
      },
      {
        name: "Name",
        value: run_config.name || "N/A",
      },
      {
        name: "Model",
        value: `${model_name(run_config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(run_config.run_config_properties.model_provider_name)})`,
      },
      {
        name: "Prompt",
        value: getRunConfigPromptDisplayName(
          run_config,
          $prompts_by_task_composite_id[
            get_task_composite_id(project_id, task?.id ?? "")
          ] ?? { generators: [], prompts: [] },
        ),
      },
      {
        name: "Tools",
        value:
          run_config.run_config_properties.tools_config?.tools &&
          run_config.run_config_properties.tools_config.tools.length > 0
            ? (() => {
                const tool_names = get_tool_names_from_ids(
                  run_config.run_config_properties.tools_config.tools,
                )
                return run_config.run_config_properties.tools_config.tools
                  .length === 1
                  ? `One tool (${tool_names.join(", ")})`
                  : `${run_config.run_config_properties.tools_config.tools.length} tools (${tool_names.join(", ")})`
              })()
            : "None",
      },
      {
        name: "Temperature",
        value: run_config.run_config_properties.temperature.toString(),
      },
      {
        name: "Top P",
        value: run_config.run_config_properties.top_p.toString(),
      },
    ]
  }

  async function archive() {
    update_archive(true)
  }

  async function unarchive() {
    update_archive(false)
  }

  async function update_archive(is_archived: boolean) {
    if (!tool_server) {
      return
    }

    const properties = tool_server.properties as KilnTaskServerProperties

    try {
      archive_error = null
      unarchive_error = null

      await client.PATCH(
        "/api/projects/{project_id}/edit_kiln_task_tool/{tool_server_id}",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
              tool_server_id: tool_server_id,
            },
          },
          body: {
            name: String(properties.name || ""),
            description: String(properties.description || ""),
            task_id: String(properties.task_id || ""),
            run_config_id: String(properties.run_config_id || ""),
            is_archived: is_archived,
          },
        },
      )
    } catch (e) {
      if (is_archived) {
        archive_error = createKilnError(e)
      } else {
        unarchive_error = createKilnError(e)
      }
    } finally {
      fetch_tool_server()
      // Re-load available tools to make sure archived tools aren't shown
      if (project_id) {
        load_available_tools(project_id, true)
      }
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={"Kiln Task as Tool"}
    subtitle={`Name: ${tool_server?.name || ""}`}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/agents#multi-actor-interaction-aka-subtasks"
    breadcrumbs={[
      {
        label: "Settings",
        href: `/settings`,
      },
      {
        label: "Manage Tools",
        href: `/settings/manage_tools/${project_id}`,
      },
      {
        label: "Kiln Task Tools",
        href: `/settings/manage_tools/${project_id}/kiln_task_tools`,
      },
    ]}
    action_buttons={[
      {
        label: "Clone",
        handler: clone_tool,
      },
      {
        label: is_archived ? "Unarchive" : "Archive",
        handler: is_archived ? unarchive : archive,
      },
    ]}
  >
    {#if archive_error}
      <Warning
        warning_message={archive_error.getMessage() ||
          "An unknown error occurred"}
        large_icon={true}
        warning_color="error"
        outline={true}
      />
    {/if}
    {#if unarchive_error}
      <Warning
        warning_message={unarchive_error.getMessage() ||
          "An unknown error occurred"}
        large_icon={true}
        warning_color="error"
        outline={true}
      />
    {/if}
    {#if is_archived}
      <Warning
        warning_message="This Kiln task tool is archived. You may unarchive it to use it again."
        large_icon={true}
        warning_color="warning"
        outline={true}
      />
    {/if}
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task Tool</div>
        <div class="text-error text-sm">
          {loading_error.getMessage() || "An unknown error occurred"}
        </div>
        <button class="btn btn-primary mt-4" on:click={go_back}>
          Back to Tools
        </button>
      </div>
    {:else if tool_server}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-6">
        <div class="w-full xl:flex-1 flex flex-col gap-6">
          <PropertyList
            properties={get_tool_properties(tool_server)}
            title="Tool Properties"
          />
        </div>
        <div class="w-full xl:flex-shrink-0 xl:max-w-96 flex flex-col gap-6">
          <PropertyList
            properties={get_task_properties(task)}
            title="Task Properties"
          />
          <PropertyList
            properties={get_run_config_properties(run_config)}
            title="Run Configuration"
          />
        </div>
      </div>
    {:else}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Kiln Task Tool Not Found</div>
        <div class="text-gray-500 text-sm">
          The requested tool could not be found.
        </div>
        <button class="btn btn-primary mt-4" on:click={go_back}>
          Back to Tools
        </button>
      </div>
    {/if}
  </AppPage>
</div>
