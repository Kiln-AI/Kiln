<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type { ExternalToolServerApiDescription } from "$lib/types"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import { uncache_available_tools } from "$lib/stores"

  $: project_id = $page.params.project_id
  $: tool_server_id = $page.params.tool_server_id

  let tool_server: ExternalToolServerApiDescription | null = null
  let loading = true
  let error: KilnError | null = null
  let delete_dialog: DeleteDialog | null = null
  $: delete_url = `/api/projects/${project_id}/tool_servers/${tool_server_id}`

  onMount(async () => {
    await fetch_tool_server()
  })

  async function fetch_tool_server() {
    try {
      loading = true
      error = null

      if (!project_id) {
        throw new Error("No project ID provided")
      }

      if (!tool_server_id) {
        throw new Error("No tool server ID provided")
      }

      // Fetch the specific tool by ID
      const { data, error: fetch_error } = await client.GET(
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

      if (fetch_error) {
        throw fetch_error
      }

      tool_server = data as ExternalToolServerApiDescription
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function goBack() {
    goto(`/settings/manage_tools/${project_id}`)
  }

  function getTaskProperties(tool: ExternalToolServerApiDescription) {
    const properties = [
      { name: "ID", value: tool.id || "Unknown" },
      { name: "Name", value: tool.name || "Unknown" },
      {
        name: "Description",
        value: tool.description || "N/A",
      },
    ]

    // Add tool-specific properties
    if (tool.properties["task_id"]) {
      properties.push({
        name: "Task ID",
        value: tool.properties["task_id"],
      })
    }

    if (tool.properties["run_config_id"]) {
      properties.push({
        name: "Run Config ID",
        value: tool.properties["run_config_id"],
      })
    }

    if (tool.created_at) {
      properties.push({
        name: "Created At",
        value: new Date(tool.created_at).toLocaleString(),
      })
    }

    if (tool.created_by) {
      properties.push({
        name: "Created By",
        value: tool.created_by,
      })
    }

    return properties
  }

  function afterDelete() {
    // Delete the project_id from the available_tools, so next reload it loads the updated list.
    uncache_available_tools(project_id)

    goto(`/settings/manage_tools/${project_id}`)
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
    ]}
    action_buttons={[
      {
        label: "Edit",
        href: `/settings/manage_tools/${project_id}/edit_tool_server/${tool_server?.id}`,
      },
      {
        icon: "/images/delete.svg",
        handler: () => delete_dialog?.show(),
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task Tool</div>
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
        <button class="btn btn-primary mt-4" on:click={goBack}>
          Back to Tools
        </button>
      </div>
    {:else if tool_server}
      <!-- Row 1: Tool Properties -->
      <div class="flex flex-col lg:flex-row gap-8 lg:gap-16 mb-10">
        <div class="flex-1">
          <PropertyList
            properties={getTaskProperties(tool_server)}
            title="Tool Properties"
          />
        </div>
      </div>
    {:else}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Task Tool Not Found</div>
        <div class="text-gray-500 text-sm">
          The requested task tool could not be found.
        </div>
        <button class="btn btn-primary mt-4" on:click={goBack}>
          Back to Tools
        </button>
      </div>
    {/if}
  </AppPage>
</div>

<DeleteDialog
  name="Task Tool"
  bind:this={delete_dialog}
  {delete_url}
  after_delete={afterDelete}
/>
