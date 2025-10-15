<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { ExternalToolServerApiDescription } from "$lib/types"
  import EditLocalTool from "../../add_tools/local_mcp/edit_local_tool.svelte"
  import EditRemoteTool from "../../add_tools/remote_mcp/edit_remote_tool.svelte"

  $: tool_server_id = $page.params.tool_server_id
  $: project_id = $page.params.project_id

  let loading = true
  let error: KilnError | null = null
  let tool_server: ExternalToolServerApiDescription | null = null

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
        throw new Error("No tool ID provided")
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

  // I don't care that much about dynamic name, but the exhaustive checking forces us to remember this screen when adding a new tool server type
  function edit_server_subtitle(
    tool_server: ExternalToolServerApiDescription | null,
  ): string | undefined {
    if (!tool_server) {
      return undefined
    }
    switch (tool_server.type) {
      case "local_mcp":
        return "Local MCP Server: " + tool_server.name
      case "remote_mcp":
        return "Remote MCP Server: " + tool_server.name
      case "kiln_task":
        return "Kiln Task: " + tool_server.name
      default: {
        const exhaustiveCheck: never = tool_server.type
        console.warn(`Unhandled toolType: ${exhaustiveCheck}`)
        return "Tool Server: " + tool_server.name
      }
    }
  }
</script>

<AppPage title="Edit Tool Server" subtitle={edit_server_subtitle(tool_server)}>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error || !tool_server}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Tool Server</div>
      <div class="text-error text-sm">
        {error?.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if tool_server.type === "local_mcp"}
    <EditLocalTool editing_tool_server={tool_server} />
  {:else if tool_server.type === "remote_mcp"}
    <EditRemoteTool editing_tool_server={tool_server} />
  {/if}
</AppPage>
