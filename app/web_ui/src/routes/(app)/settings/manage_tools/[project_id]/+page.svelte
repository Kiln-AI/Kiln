<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type { KilnToolDescription } from "$lib/types"
  import { toolTypeToString } from "$lib/utils/formatters"
  import EmptyTools from "./empty_tools.svelte"

  $: project_id = $page.params.project_id
  $: is_empty = !tools || tools.length == 0

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

      if (!project_id) {
        throw new Error("No project ID provided")
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

  function navigateToTool(tool: KilnToolDescription) {
    if (tool.id) {
      goto(`/settings/manage_tools/${project_id}/tools/${tool.id}`)
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Tools"
    subtitle="Connect your project to tools with MCP servers"
    action_buttons={is_empty
      ? []
      : [
          {
            label: "Add Tool",
            href: `/settings/manage_tools/${project_id}/add_tools`,
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
      <div class="overflow-x-auto rounded-lg border mt-4">
        <table class="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {#each tools as tool}
              <tr
                class="hover:bg-base-200 cursor-pointer"
                on:click={() => navigateToTool(tool)}
                on:keydown={(e) => e.key === "Enter" && navigateToTool(tool)}
                role="button"
                tabindex="0"
              >
                <td class="font-medium">{tool.name}</td>
                <td class="text-sm">{toolTypeToString(tool.type)}</td>
                <td class="text-sm">
                  {tool.description || "No description available"}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if is_empty}
      <div class="flex flex-col items-center justify-center min-h-[60vh]">
        <EmptyTools {project_id} />
      </div>
    {/if}
  </AppPage>
</div>
