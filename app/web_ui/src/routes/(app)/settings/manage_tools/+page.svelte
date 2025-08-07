<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { ui_state } from "$lib/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import type { KilnToolDescription } from "$lib/types"

  let tools: KilnToolDescription[] | null = null
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    await fetch_available_tools()
  })

  async function fetch_available_tools() {
    try {
      loading = true
      error = null

      const project_id = $ui_state?.current_project_id
      if (!project_id) {
        throw new Error("No current project selected")
      }

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

      tools = data
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Tools"
    sub_subtitle="Connect your projects to tools like remote MCP servers, Kiln built-in tools, and more"
    action_buttons={[
      {
        label: "Add Tool",
        href: "/settings/tools/add_tool",
        primary: true,
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
        <div class="font-medium">Error Loading Tools</div>
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else if tools && tools.length > 0}
      <div class="flex flex-col gap-6 max-w-[800px] mx-auto">
        {#each tools as tool}
          <div
            class="card card-bordered border-base-300 bg-base-200 shadow-md w-full p-6"
          >
            <div class="flex flex-col">
              <div class="font-medium text-lg">
                {tool.name}
              </div>
              <div class="text-sm text-gray-500 mt-1">
                Type: {tool.id}
              </div>
              <div class="font-light pt-2">
                {tool.description || "No description available"}
              </div>
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <div class="font-light text-gray-500 text-sm">
        No available tools found for this project.{" "}
        <a href="/settings/tools/add_tool" class="link"> Add one now </a>
        .
      </div>
    {/if}
  </AppPage>
</div>
