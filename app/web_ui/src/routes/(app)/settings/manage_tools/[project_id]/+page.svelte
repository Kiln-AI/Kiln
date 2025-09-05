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
  import Warning from "$lib/ui/warning.svelte"
  import { uncache_available_tools } from "$lib/stores"

  $: project_id = $page.params.project_id
  $: is_empty = !demo_tools_enabled && (!tools || tools.length == 0)

  let tools: KilnToolServerDescription[] | null = null
  let demo_tools_enabled: boolean | null = null
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    await fetch_available_tool_servers()
    await load_demo_tools()
    loading = false
  })

  async function fetch_available_tool_servers() {
    try {
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
    }
  }

  async function load_demo_tools() {
    try {
      const { data, error } = await client.GET("/api/demo_tools")
      if (error) {
        throw error
      }
      demo_tools_enabled = data
    } catch (error) {
      console.error(error)
    }
  }

  function navigateToToolServer(tool_server: KilnToolServerDescription) {
    if (tool_server.id) {
      goto(
        `/settings/manage_tools/${project_id}/tool_servers/${tool_server.id}`,
      )
    }
  }

  async function disable_demo_tools() {
    try {
      demo_tools_enabled = false
      const { error } = await client.POST("/api/demo_tools", {
        params: {
          query: {
            enable_demo_tools: false,
          },
        },
      })
      if (error) {
        throw error
      }
      // Delete the project_id from the available_tools, so next load it loads the updated list.
      uncache_available_tools(project_id)
    } catch (error) {
      console.error(error)
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
    {:else if !is_empty}
      <div class="overflow-x-auto rounded-lg border mt-4">
        <table class="table">
          <thead>
            <tr>
              <th>Server Name</th>
              <th>Type</th>
              <th>Description</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {#each tools || [] as tool}
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
                <td class="text-sm">
                  {#if tool.missing_secrets && tool.missing_secrets.length > 0}
                    <Warning
                      warning_message="Action Required"
                      warning_color="warning"
                      tight={true}
                    />
                  {:else}
                    <Warning
                      warning_message="Ready"
                      warning_color="success"
                      warning_icon="check"
                      tight={true}
                    />
                  {/if}
                </td>
              </tr>
            {/each}
            {#if demo_tools_enabled}
              <tr>
                <td class="font-medium">Math Demo Tools</td>
                <td class="text-sm">Built-in Tools</td>
                <td class="text-sm"
                  >Basic math tools: add, subtract, multiply, divide.
                  <button
                    class="link text-gray-500"
                    on:click={disable_demo_tools}
                  >
                    Disable
                  </button>
                </td>
                <td class="text-sm">
                  <Warning
                    warning_message="Ready"
                    warning_color="success"
                    warning_icon="check"
                    tight={true}
                  />
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
    {:else}
      <div class="flex flex-col items-center justify-center min-h-[60vh]">
        <EmptyTools {project_id} />
      </div>
    {/if}
  </AppPage>
</div>
