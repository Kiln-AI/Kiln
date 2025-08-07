<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type { KilnToolDescription } from "$lib/types"

  $: project_id = $page.params.project_id
  $: tool_id = $page.params.tool_id

  let tool: KilnToolDescription | null = null
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

      // Fetch all available tools and find the specific one
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/available_tools",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        throw fetch_error
      }

      // Find the specific tool by ID
      const foundTool = data?.find((t) => t.id === tool_id)
      if (!foundTool) {
        throw new Error(`Tool with ID "${tool_id}" not found`)
      }

      tool = foundTool
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function goBack() {
    goto(`/settings/manage_tools/${project_id}`)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={tool?.name || "Tool Details"}
    subtitle="Tool Information"
    action_buttons={[
      {
        label: "Back to Tools",
        href: `/settings/manage_tools/${project_id}`,
        primary: false,
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
            <h2 class="card-title text-xl mb-4">Tool Information</h2>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div class="font-medium text-sm mb-1">Name</div>
                <div class="text-lg">{tool.name}</div>
              </div>

              <div>
                <div class="font-medium text-sm mb-1">ID</div>
                <div class="text-sm font-mono text-gray-600">{tool.id}</div>
              </div>

              <div>
                <div class="font-medium text-sm mb-1">Type</div>
                <div class="badge badge-outline">{tool.type}</div>
              </div>

              <div class="md:col-span-2">
                <div class="font-medium text-sm mb-1">Description</div>
                <div class="text-sm">
                  {tool.description || "No description available"}
                </div>
              </div>
            </div>
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
