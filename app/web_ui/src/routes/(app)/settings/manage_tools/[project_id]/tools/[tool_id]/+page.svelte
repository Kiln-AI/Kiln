<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type { ExternalTool } from "$lib/types"
  import { toolTypeToString } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id
  $: tool_id = $page.params.tool_id

  let tool: ExternalTool | null = null
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    await fetch_tool()
  })

  async function fetch_tool() {
    try {
      loading = true
      error = null

      if (!project_id) {
        throw new Error("No project ID provided")
      }

      if (!tool_id) {
        throw new Error("No tool ID provided")
      }

      // Fetch the specific tool by ID
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tools/{tool_id}",
        {
          params: {
            path: {
              project_id,
              tool_id,
            },
          },
        },
      )

      if (fetch_error) {
        throw fetch_error
      }

      tool = data as ExternalTool
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function goBack() {
    goto(`/settings/manage_tools/${project_id}`)
  }

  function getDetailsProperties(tool: ExternalTool) {
    const properties = [
      { name: "ID", value: tool.id || "Unknown" },
      { name: "Name", value: tool.name || "Unknown" },
      {
        name: "Description",
        value: tool.description || "N/A",
      },
    ]

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

  function getConnectionProperties(tool: ExternalTool) {
    const properties = [
      { name: "Type", value: toolTypeToString(tool.type) || "Unknown" },
    ]

    if (tool.properties["server_url"]) {
      properties.push({
        name: "Server URL",
        value: tool.properties["server_url"],
      })
    }

    return properties
  }
  function getHeadersProperties(tool: ExternalTool) {
    return Object.entries(tool.properties["headers"] || {}).map(
      ([key, value]) => ({
        name: key,
        value: String(value || "N/A"),
      }),
    )
  }
</script>

<div class="max-w-[1400px]">
  <AppPage title={"Tool"} subtitle={`Name: ${tool?.name || ""}`}>
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Tool</div>
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
        <button class="btn btn-primary mt-4" on:click={goBack}>
          Back to Tools
        </button>
      </div>
    {:else if tool}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-10">
        <div class="grow flex flex-col">
          <PropertyList
            properties={getDetailsProperties(tool)}
            title="Properties"
          />
        </div>
        <div class="grow flex flex-col">
          {#if tool.type === "remote_mcp"}
            <PropertyList
              properties={getConnectionProperties(tool)}
              title="Connection Details"
            />
            {#if getHeadersProperties(tool).length > 0}
              <!-- Manually add a gap between the connection details and the headers -->
              <div class="mt-8">
                <PropertyList
                  properties={getHeadersProperties(tool)}
                  title="Headers"
                />
              </div>
            {/if}
          {/if}
        </div>
      </div>
    {:else}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Tool Not Found</div>
        <div class="text-gray-500 text-sm">
          The requested tool could not be found.
        </div>
        <button class="btn btn-primary mt-4" on:click={goBack}>
          Back to Tools
        </button>
      </div>
    {/if}
  </AppPage>
</div>
