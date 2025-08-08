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

  function getToolProperties(tool: ExternalTool) {
    const properties = [
      { name: "Name", value: tool.name || "Unknown" },
      {
        name: "Description",
        value: tool.description || "N/A",
      },
      { name: "ID", value: tool.id || "Unknown" },
      { name: "Type", value: toolTypeToString(tool.type) || "Unknown" },
      { name: "Version", value: tool.v || "Unknown" },
      { name: "Model Type", value: tool.model_type || "Unknown" },
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
</script>

<div class="max-w-[1400px]">
  <AppPage title={"Tool Details"}>
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
      <div class="space-y-6 mt-6">
        <!-- Tool Information Card -->
        <div class="card bg-base-100 border">
          <div class="card-body">
            <PropertyList
              properties={getToolProperties(tool)}
              title="Tool Information"
            />

            {#if tool.properties && Object.keys(tool.properties).length > 0}
              <div class="mt-6">
                <div class="text-xl font-bold mb-4">Properties</div>
                <div class="bg-base-200 rounded p-3">
                  <pre class="text-xs overflow-x-auto">{JSON.stringify(
                      tool.properties,
                      null,
                      2,
                    )}</pre>
                </div>
              </div>
            {/if}
          </div>
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
