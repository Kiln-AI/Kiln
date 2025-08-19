<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import type { ExternalToolServerApiDescription } from "$lib/types"
  import { toolServerTypeToString } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id
  $: tool_server_id = $page.params.tool_server_id

  let tool_server: ExternalToolServerApiDescription | null = null
  let loading = true
  let error: KilnError | null = null

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

  function goBack() {
    goto(`/settings/manage_tools/${project_id}`)
  }

  function getDetailsProperties(tool: ExternalToolServerApiDescription) {
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

  function getConnectionProperties(tool: ExternalToolServerApiDescription) {
    const properties = [
      { name: "Type", value: toolServerTypeToString(tool.type) || "Unknown" },
    ]

    if (tool.properties["server_url"]) {
      properties.push({
        name: "Server URL",
        value: tool.properties["server_url"],
      })
    }

    return properties
  }
  function getHeadersProperties(tool: ExternalToolServerApiDescription) {
    return Object.entries(tool.properties["headers"] || {}).map(
      ([key, value]) => ({
        name: key,
        value: String(value || "N/A"),
      }),
    )
  }

  function formatToolArguments(inputSchema: Record<string, unknown>): string {
    if (!inputSchema || !inputSchema.properties) {
      return ""
    }

    const properties = inputSchema.properties as Record<string, unknown>
    const required = (inputSchema.required as string[]) || []

    return Object.entries(properties)
      .map(([name, schema]) => {
        const schemaObj = schema as Record<string, unknown>
        const isRequired = required.includes(name)
        const type = (schemaObj.type as string) || "unknown"
        const description = (schemaObj.description as string) || ""
        return `${name}${isRequired ? "*" : ""} (${type})${description ? `: ${description}` : ""}`
      })
      .join("|||") // Use a delimiter that we can split on later
  }
</script>

<div class="max-w-[1400px]">
  <AppPage title={"Tool Server"} subtitle={`Name: ${tool_server?.name || ""}`}>
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
    {:else if tool_server}
      <!-- Row 1: Properties and Connection Details side by side -->
      <div class="flex flex-col lg:flex-row gap-8 lg:gap-16 mb-10">
        <div class="flex-1">
          <PropertyList
            properties={getDetailsProperties(tool_server)}
            title="Properties"
          />
        </div>
        <div class="flex-1">
          {#if tool_server.type === "remote_mcp"}
            <PropertyList
              properties={getConnectionProperties(tool_server)}
              title="Connection Details"
            />
            {#if getHeadersProperties(tool_server).length > 0}
              <!-- Manually add a gap between the connection details and the headers -->
              <div class="mt-8">
                <PropertyList
                  properties={getHeadersProperties(tool_server)}
                  title="Headers"
                />
              </div>
            {/if}
          {/if}
        </div>
      </div>
      <!-- Row 2: Available Tools full width -->
      <div class="mb-10">
        <h3 class="text-xl font-bold mb-4">Available Tools</h3>
        {#if tool_server.available_tools.length > 0}
          <div class="overflow-x-auto rounded-lg border">
            <table class="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Description</th>
                  <th>Arguments</th>
                </tr>
              </thead>
              <tbody>
                {#each tool_server.available_tools as tool}
                  <tr>
                    <td class="font-medium">{tool.name}</td>
                    <td>{tool.description || "N/A"}</td>
                    <td>
                      {#if formatToolArguments(tool.inputSchema || {})}
                        <ul class="list-disc list-inside">
                          {#each formatToolArguments(tool.inputSchema || {}).split("|||") as arg}
                            <li class="text-sm">{arg}</li>
                          {/each}
                        </ul>
                      {:else}
                        <span class="text-gray-500">N/A</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <div class="text-lg mb-4 text-gray-500">
            This server does not expose any tools
          </div>
        {/if}
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
