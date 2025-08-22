<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type { KilnToolServerDescription } from "$lib/types"
  import { toolServerTypeToString } from "$lib/utils/formatters"
  import EmptyTools from "./empty_tools.svelte"

  $: project_id = $page.params.project_id
  $: is_empty = !tools || tools.length == 0

  let tools: KilnToolServerDescription[] | null = null
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    await fetch_available_tool_servers()
  })

  async function fetch_available_tool_servers() {
    try {
      loading = true
      error = null

      if (!project_id) {
        throw new Error("No project ID provided")
      }

      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/available_tool_servers",
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

  function navigateToToolServer(tool_server: KilnToolServerDescription) {
    if (tool_server.id) {
      goto(
        `/settings/manage_tools/${project_id}/tool_servers/${tool_server.id}`,
      )
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Manage Tools"
    subtitle="Connect your project to tools with MCP servers"
    action_buttons={is_empty
      ? []
      : [
          {
            label: "Add Tools",
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
              <th>Server Name</th>
              <th>Type</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {#each tools as tool}
              <tr
                class="hover:bg-base-200 cursor-pointer"
                on:click={() => navigateToToolServer(tool)}
                on:keydown={(e) =>
                  e.key === "Enter" && navigateToToolServer(tool)}
                role="button"
                tabindex="0"
              >
                <td class="font-medium">{tool.name}</td>
                <td class="text-sm">{toolServerTypeToString(tool.type)}</td>
                <td class="text-sm">{tool.description || "N/A"}</td>
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
