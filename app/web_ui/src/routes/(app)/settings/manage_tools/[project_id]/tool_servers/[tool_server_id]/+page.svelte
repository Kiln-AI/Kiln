<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import {
    type ExternalToolServerApiDescription,
    toolIsType,
    isToolType,
  } from "$lib/types"
  import { toolServerTypeToString } from "$lib/utils/formatters"
  import type { UiProperty } from "$lib/ui/property_list"
  import { load_available_tools } from "$lib/stores"
  import Warning from "$lib/ui/warning.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { selected_tool_for_task } from "$lib/stores/tools_store"
  import TableButton from "../../../../../generate/[project_id]/[task_id]/table_button.svelte"
  import Float from "$lib/ui/float.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"

  $: project_id = $page.params.project_id!
  $: tool_server_id = $page.params.tool_server_id!
  $: is_archived = tool_server?.properties?.is_archived ?? false

  let tool_server: ExternalToolServerApiDescription | null = null
  let tool_action_dialog: Dialog
  let selected_tool_name = ""
  let loading = true
  let loading_error: KilnError | null = null
  let archive_error: KilnError | null = null
  let unarchive_error: KilnError | null = null

  onMount(async () => {
    await fetch_tool_server()
  })

  async function fetch_tool_server() {
    try {
      loading = true
      loading_error = null

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
      loading_error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function goBack() {
    goto(`/settings/manage_tools/${project_id}`)
  }

  function open_tool_action_dialog(tool_name: string) {
    selected_tool_name = tool_name
    tool_action_dialog.show()
  }

  function handleCreateTask(tool_name: string) {
    selected_tool_name = tool_name
    set_tool_store(tool_name)
    goto(
      `/settings/manage_tools/${project_id}/create_task_from_tool?tool_id=${encodeURIComponent(
        build_tool_id(tool_name),
      )}`,
    )
  }

  function set_tool_store(tool_name?: string) {
    const name = tool_name ?? selected_tool_name
    if (!name) {
      return
    }
    const tool = tool_server?.available_tools?.find(
      (available_tool) => available_tool.name === name,
    )
    if (tool) {
      selected_tool_for_task.set(tool)
    }
  }

  function build_tool_id(tool_name: string): string {
    const type_prefix = tool_server?.type === "remote_mcp" ? "remote" : "local"
    return `mcp::${type_prefix}::${tool_server_id}::${tool_name}`
  }

  $: run_with_tool_href = selected_tool_name
    ? `/run?tool_id=${encodeURIComponent(build_tool_id(selected_tool_name))}`
    : null
  $: direct_mcp_href = selected_tool_name
    ? `/settings/manage_tools/${project_id}/add_tool_to_task?tool_id=${encodeURIComponent(
        build_tool_id(selected_tool_name),
      )}`
    : null

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
      case "remote_mcp": {
        toolIsType(tool, tool.type)
        if (tool.properties.server_url) {
          properties.push({
            name: "Server URL",
            value: tool.properties.server_url,
          })
        }
        break
      }
      case "local_mcp": {
        toolIsType(tool, tool.type)
        if (tool.properties.command) {
          properties.push({
            name: "Command",
            value: tool.properties.command,
          })
        }
        const args = tool.properties.args
        if (args && isStringArray(args)) {
          properties.push({
            name: "Arguments",
            value: args.join(" ") || "None",
          })
        }
        break
      }
      case "kiln_task": {
        // Kiln task tools don't have additional properties to display
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

  /**
   * Helper function to build properties list with secret handling
   * @param nonSecretProperties - Object containing non-secret key-value pairs
   * @param secretKeys - Array of secret key names
   * @param missingSecrets - Array of missing secret key names
   * @returns Array of UiProperty objects
   */
  function buildPropertiesWithSecrets(
    nonSecretProperties: Record<string, string>,
    secretKeys: string[],
    missingSecrets: string[],
  ): UiProperty[] {
    // Non-secret values
    const properties: UiProperty[] = []
    properties.push(
      ...Object.entries(nonSecretProperties).map(([key, value]) => ({
        name: key,
        value: String(value ?? "N/A"),
      })),
    )

    // Add secret values with masked values or error state
    secretKeys.forEach((key: string) => {
      // Check if the secret is missing
      if (missingSecrets.includes(key)) {
        properties.push({
          name: key,
          value: "Value missing",
          error: true,
          link: `/settings/manage_tools/${project_id}/edit_tool_server/${tool_server_id}`,
        })
      } else if (!(key in nonSecretProperties)) {
        // Only add if not already in regular values
        properties.push({
          name: key,
          value: "●●●●●●",
        })
      }
    })

    // If the properties are empty, add a placeholder
    if (properties.length === 0) {
      properties.push({
        name: "None",
        value: " ",
      })
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

  async function archive() {
    update_archive(true)
  }

  async function unarchive() {
    update_archive(false)
  }

  async function update_archive(is_archived: boolean) {
    if (!tool_server) {
      return
    }

    try {
      archive_error = null
      unarchive_error = null

      switch (tool_server.type) {
        case "remote_mcp": {
          toolIsType(tool_server, tool_server.type)
          await client.PATCH(
            "/api/projects/{project_id}/edit_remote_mcp/{tool_server_id}",
            {
              params: {
                path: {
                  project_id,
                  tool_server_id,
                },
              },
              body: {
                name: tool_server.name,
                description: tool_server.description ?? null,
                server_url: tool_server.properties.server_url,
                headers: tool_server.properties.headers || {},
                secret_header_keys:
                  tool_server.properties.secret_header_keys || [],
                is_archived: is_archived,
              },
            },
          )
          break
        }
        case "local_mcp": {
          toolIsType(tool_server, tool_server.type)
          await client.PATCH(
            "/api/projects/{project_id}/edit_local_mcp/{tool_server_id}",
            {
              params: {
                path: {
                  project_id,
                  tool_server_id,
                },
              },
              body: {
                name: tool_server.name,
                description: tool_server.description ?? null,
                command: tool_server.properties.command,
                args: tool_server.properties.args || [],
                env_vars: tool_server.properties.env_vars || {},
                secret_env_var_keys:
                  tool_server.properties.secret_env_var_keys || [],
                is_archived: is_archived,
              },
            },
          )
          break
        }
        case "kiln_task": {
          // Kiln task tools is handled by /settings/manage_tools/[project_id]/kiln_task/[tool_server_id] page
          break
        }
        default: {
          const exhaustiveCheck: never = tool_server.type
          console.warn(`Unhandled toolType: ${exhaustiveCheck}`)
          break
        }
      }
    } catch (e) {
      if (is_archived) {
        archive_error = createKilnError(e)
      } else {
        unarchive_error = createKilnError(e)
      }
    } finally {
      fetch_tool_server()
      if (project_id) {
        load_available_tools(project_id, true)
      }
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={"Tool Server"}
    subtitle={`Name: ${tool_server?.name || ""}`}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp/running-tools-as-tasks"
    breadcrumbs={[
      {
        label: "Settings",
        href: `/settings`,
      },
      {
        label: "Manage Tools",
        href: `/settings/manage_tools/${project_id}`,
      },
    ]}
    action_buttons={[
      {
        label: "Edit",
        href: `/settings/manage_tools/${project_id}/edit_tool_server/${tool_server_id}`,
      },
      {
        label: is_archived ? "Unarchive" : "Archive",
        handler: is_archived ? unarchive : archive,
      },
    ]}
  >
    <Dialog
      bind:this={tool_action_dialog}
      title="Run Task with Tool"
      sub_subtitle="Read the Docs"
      sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp/running-tools-as-tasks"
    >
      <div class="flex flex-col gap-4">
        <a
          class="card border transition-all duration-200 hover:shadow-md hover:border-primary cursor-pointer {selected_tool_name
            ? ''
            : 'opacity-60 pointer-events-none'}"
          href={run_with_tool_href || undefined}
          on:click={() => set_tool_store()}
        >
          <div class="card-body p-4">
            <div class="text-lg font-semibold">
              Run Current Task with Tool Access
            </div>
            <div class="text-sm text-gray-500">
              Run the current task, giving the agent access to this tool.
            </div>
          </div>
        </a>
        <a
          class="card border transition-all duration-200 hover:shadow-md hover:border-primary cursor-pointer {selected_tool_name
            ? ''
            : 'opacity-60 pointer-events-none'}"
          href={direct_mcp_href || undefined}
          on:click={() => set_tool_store()}
        >
          <div class="card-body p-4">
            <div class="text-lg font-semibold">Run Tool Directly</div>
            <div class="text-sm text-gray-500">
              Setup a run configuration for a task to call this tool directly,
              without a wrapper agent. Useful for evaluating external APIs or
              agents.
            </div>
          </div>
        </a>
      </div>
    </Dialog>
    {#if archive_error}
      <Warning
        warning_message={archive_error.getMessage() ||
          "An unknown error occurred"}
        large_icon={true}
        warning_color="error"
        outline={true}
      />
    {/if}
    {#if unarchive_error}
      <Warning
        warning_message={unarchive_error.getMessage() ||
          "An unknown error occurred"}
        large_icon={true}
        warning_color="error"
        outline={true}
      />
    {/if}
    {#if is_archived}
      <Warning
        warning_message="This tool server is archived. You may unarchive it to use it again."
        large_icon={true}
        warning_color="warning"
        outline={true}
      />
    {/if}
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <ErrorDetailsBlock
        title="Error Loading Tool Server"
        error_messages={loading_error.getErrorMessages()}
        troubleshooting_steps={[
          "Review the configuration using the **Edit** button at the top of this page.",
          "If the server is unavailable, try again later.",
          "Check Kiln logs for more details.",
        ]}
        markdown={true}
        trusted={true}
      />
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
          {#if tool_server.type === "remote_mcp" && isToolType(tool_server, tool_server.type)}
            <PropertyList
              properties={getConnectionProperties(tool_server)}
              title="Connection Details"
            />
            <!-- Manually add a gap between the connection details and the headers -->
            <div class="mt-8">
              <PropertyList
                properties={buildPropertiesWithSecrets(
                  tool_server.properties.headers || {},
                  tool_server.properties.secret_header_keys || [],
                  tool_server.missing_secrets,
                )}
                title="Headers"
              />
            </div>
          {:else if tool_server.type === "local_mcp" && isToolType(tool_server, tool_server.type)}
            <PropertyList
              properties={getConnectionProperties(tool_server)}
              title="Run Configuration"
            />
            <!-- Check if there are any environment variables or secret environment variables -->
            <div class="mt-8">
              <PropertyList
                properties={buildPropertiesWithSecrets(
                  tool_server.properties.env_vars || {},
                  tool_server.properties.secret_env_var_keys || [],
                  tool_server.missing_secrets,
                )}
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
                  {#if tool_server?.type === "remote_mcp" || tool_server?.type === "local_mcp"}
                    <th></th>
                  {/if}
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
                    {#if tool_server?.type === "remote_mcp" || tool_server?.type === "local_mcp"}
                      <td class="p-0">
                        <div class="dropdown dropdown-end dropdown-hover">
                          <TableButton />
                          <Float>
                            <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                            <ul
                              tabindex="0"
                              class="dropdown-content menu bg-base-100 rounded-box z-[1] w-64 p-2 shadow"
                            >
                              <li>
                                <button
                                  on:click={() =>
                                    open_tool_action_dialog(tool.name)}
                                >
                                  Run Task with Tool
                                </button>
                              </li>
                              <li>
                                <button
                                  on:click={() => handleCreateTask(tool.name)}
                                >
                                  Create Task from Tool
                                </button>
                              </li>
                            </ul>
                          </Float>
                        </div>
                      </td>
                    {/if}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <div class="text-lg mb-4 text-gray-500">
            This server has no tools.
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
