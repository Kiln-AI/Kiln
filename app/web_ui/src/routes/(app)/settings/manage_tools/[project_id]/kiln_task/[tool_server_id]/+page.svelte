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
  } from "$lib/types"
  import {
    current_task_prompts,
    load_available_prompts,
    load_available_models,
    load_model_info,
    model_info,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import Warning from "$lib/ui/warning.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import {
    get_task_composite_id,
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"

  $: project_id = $page.params.project_id
  $: tool_server_id = $page.params.tool_server_id

  let task_name = ""
  let run_config: TaskRunConfig | null = null
  let tool_server: ExternalToolServerApiDescription | null = null
  let loading = true
  let loading_error: KilnError | null = null
  // TODO: Use these errors
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  let archive_error: KilnError | null = null
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  let unarchive_error: KilnError | null = null

  onMount(async () => {
    await fetch_tool_server()
    await load_available_prompts()
    await load_available_models()
    await load_model_info()
  })

  $: if (tool_server) {
    const task_id = tool_server.properties["task_id"] as string
    if (task_id) {
      get_task(task_id)
        .then((task) => {
          task_name = task.name
        })
        .catch((err) => {
          console.error("Failed to fetch task:", err)
        })

      const run_config_id = tool_server.properties["run_config_id"] as string
      if (run_config_id) {
        load_task_run_configs(project_id, task_id).then(() => {
          const run_configs =
            $run_configs_by_task_composite_id[
              get_task_composite_id(project_id, task_id)
            ]
          run_config =
            run_configs?.find((rc) => rc.id === run_config_id) || null
        })
      }
    }
  }

  // TODO: Move this to a shared component since other places use it too
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

  function get_task_properties(tool: ExternalToolServerApiDescription) {
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

    if (!tool_server) {
      return
    }

    try {
      await client.PATCH(
        "/api/projects/{project_id}/edit_kiln_task/{tool_server_id}",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
              tool_server_id: tool_server_id,
            },
          },
          body: {
            name: String(tool_server.properties["name"]),
            description: String(tool_server.properties["description"]),
            task_id: String(tool_server.properties["task_id"]),
            run_config_id: String(tool_server.properties["run_config_id"]),
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
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={"Kiln Task Tool"}
    subtitle={`Name: ${tool_server?.name || ""}`}
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
        label: tool_server?.properties["is_archived"] ? "Unarchive" : "Archive",
        handler: tool_server?.properties["is_archived"] ? unarchive : archive,
      },
    ]}
  >
    {#if tool_server?.properties["is_archived"]}
      <Warning
        warning_message="This Kiln Task tool is archived. You may unarchive it to use it again."
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
      <div class="flex flex-col lg:flex-row gap-8 xl:gap-12">
        <div class="flex-1">
          <div class="text-xl font-bold mb-1">
            Task: {task_name}
          </div>
          {#if run_config && $model_info}
            <div class="text-sm text-gray-500 mt-2 mb-2">
              {`Model: ${model_name(run_config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(run_config.run_config_properties.model_provider_name)})`}
            </div>
            <div class="text-sm text-gray-500 mb-2">
              {`Prompt: ${getRunConfigPromptDisplayName(run_config, $current_task_prompts)}`}
            </div>
            <div class="text-sm text-gray-500 mb-2">
              {`Tools: ${run_config.run_config_properties.tools_config?.tools && run_config.run_config_properties.tools_config.tools.length > 0 ? run_config.run_config_properties.tools_config.tools.join(", ") : "None"}`}
            </div>
            <div class="text-sm text-gray-500 mb-2">
              {`Temperature: ${run_config.run_config_properties.temperature}`}
            </div>
            <div class="text-sm text-gray-500 mb-2">
              {`Top P: ${run_config.run_config_properties.top_p}`}
            </div>
          {:else}
            <div class="text-sm text-gray-500 mb-2">Run Config Not Found</div>
          {/if}
        </div>
        <div class="w-full lg:w-80 xl:w-96 flex-shrink-0 flex flex-col gap-6">
          <PropertyList
            properties={get_task_properties(tool_server)}
            title="Properties"
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
