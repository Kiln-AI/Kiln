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

    switch (tool.type) {
      case "remote_mcp":
        if (tool.properties["server_url"]) {
          properties.push({
            name: "Server URL",
            value: tool.properties["server_url"],
          })
        }
        break
      case "local_mcp": {
        if (tool.properties["command"]) {
          properties.push({
            name: "Command",
            value: tool.properties["command"],
          })
        }
        const args = tool.properties["args"]
        if (args && isStringArray(args)) {
          properties.push({
            name: "Arguments",
            value: (args as string[]).join(" ") || "None",
          })
        }
        break
      }
      default: {
        // This ensures exhaustive checking - if you add a new case to StructuredOutputMode
        // and don't handle it above, TypeScript will error here
        const exhaustiveCheck: never = tool.type
        console.warn(`Unhandled toolType: ${exhaustiveCheck}`)
        break
      }
    }

    return properties
  }

  interface Argument {
    name: string
    type: string
    description: string | null
    isRequired: boolean
  }

  // Type guard functions for safe type checking
  function isStringArray(value: unknown): value is string[] {
    return (
      Array.isArray(value) && value.every((item) => typeof item === "string")
    )
  }

  function isObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === "object" && !Array.isArray(value)
  }

  function isString(value: unknown): value is string {
    return typeof value === "string"
  }

  function formatToolArguments(
    inputSchema: Record<string, unknown>,
  ): Argument[] {
    if (!isObject(inputSchema) || !isObject(inputSchema.properties)) {
      return []
    }

    const properties = inputSchema.properties
    const required = isStringArray(inputSchema.required)
      ? inputSchema.required
      : []

    const args: Argument[] = []

    for (const [name, schema] of Object.entries(properties)) {
      if (!isObject(schema)) {
        continue
      }

      const isRequired = required.includes(name)
      const type = isString(schema.type) ? schema.type : "Unknown"
      const description = isString(schema.description)
        ? schema.description
        : null
      args.push({ name, type, description, isRequired })
    }
    return args
  }

  function afterDelete() {
    // Delete the project_id from the available_tools, so next reload it loads the updated list.
    uncache_available_tools(project_id)

    goto(`/settings/manage_tools/${project_id}`)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={"Tool Server"}
    subtitle={`Name: ${tool_server?.name || ""}`}
    action_buttons={[
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
            <!-- Manually add a gap between the connection details and the headers -->
            <div class="mt-8">
              <PropertyList
                properties={Object.entries(
                  tool_server.properties["headers"] || {},
                ).map(([key, value]) => ({
                  name: key,
                  value: String(value ?? "N/A"),
                }))}
                title="Headers"
              />
            </div>
          {:else if tool_server.type === "local_mcp"}
            <PropertyList
              properties={getConnectionProperties(tool_server)}
              title="Run Configuration"
            />
            <div class="mt-8">
              <PropertyList
                properties={Object.entries(
                  tool_server.properties["env_vars"] || {},
                ).map(([key, value]) => ({
                  name: key,
                  value: String(value ?? "N/A"),
                }))}
                title="Environment Variables"
              />
            </div>
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
                  {@const formatted_args = formatToolArguments(
                    tool.inputSchema || {},
                  )}
                  <tr>
                    <td class="font-medium">{tool.name}</td>
                    <td class="max-w-[300px]">{tool.description || "None"}</td>
                    <td>
                      {#if formatted_args.length > 0}
                        <div class="divide-y divide-y-[0.5px]">
                          {#each formatted_args as arg}
                            <div class="py-2">
                              <div class="flex flex-row gap-3 items-center">
                                <span class="font-mono">{arg.name}</span>
                                <span class="font-mono font-light text-gray-500"
                                  >{arg.type}
                                </span>
                                {#if !arg.isRequired}
                                  <span class="badge badge-sm badge-outline"
                                    >Optional</span
                                  >
                                {/if}
                              </div>
                              {#if arg.description}
                                <div class="text-gray-500 text-sm mt-1">
                                  {arg.description}
                                </div>
                              {/if}
                            </div>
                          {/each}
                        </div>
                      {:else}
                        <span class="text-gray-500">None</span>
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

<DeleteDialog
  name="Tool Server"
  bind:this={delete_dialog}
  {delete_url}
  after_delete={afterDelete}
/>
