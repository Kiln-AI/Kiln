<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"
  import CodeToolTestPanel from "$lib/components/code_tools/code_tool_test_panel.svelte"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { formatDate } from "$lib/utils/formatters"
  import {
    load_available_tools,
    uncache_available_tools,
    available_tools,
    ui_state,
  } from "$lib/stores"
  import type {
    CodeToolResponse,
    ToolApiDescription,
    ToolSetType,
  } from "$lib/types"
  import { tool_link, tool_set_type_label } from "$lib/utils/link_builder"
  import posthog from "posthog-js"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: code_tool_id = $page.params.code_tool_id!
  $: agentInfo.set({
    name: "Code Tool Detail",
    description: `Code tool detail for tool ID ${code_tool_id} in project ID ${project_id}. Tool name: ${code_tool?.name ?? "[loading]"}.`,
  })

  let code_tool: CodeToolResponse | null = null
  let loading = true
  let loading_error: KilnError | null = null
  let archive_loading = false
  let archive_error: KilnError | null = null
  let edit_dialog: EditDialog

  $: is_archived = code_tool?.is_archived ?? false

  $: if (project_id && code_tool_id) {
    fetch_code_tool()
  }

  async function fetch_code_tool() {
    try {
      loading = true
      loading_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/code_tools/{code_tool_id}",
        {
          params: {
            path: { project_id, code_tool_id },
          },
        },
      )
      if (error) throw error
      code_tool = data
    } catch (err) {
      loading_error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  async function toggle_archive() {
    if (!code_tool) return
    archive_loading = true
    archive_error = null
    try {
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/code_tools/{code_tool_id}/archive",
        {
          params: {
            path: { project_id, code_tool_id },
          },
          body: { archived: !is_archived },
        },
      )
      if (error) throw error
      code_tool = data
      posthog.capture("archive_code_tool", {
        project_id,
        code_tool_id,
        archived: data.is_archived,
      })
      uncache_available_tools(project_id)
      await load_available_tools(project_id, true)
    } catch (err) {
      archive_error = createKilnError(err)
    } finally {
      archive_loading = false
    }
  }

  function handle_clone() {
    if (!code_tool) return
    posthog.capture("clone_code_tool", {
      project_id,
      code_tool_id,
    })
    goto(`/tools/${project_id}/add_tools/code_tool`, {
      state: {
        name: `${code_tool.name} (copy)`,
        tool_function_name: is_archived
          ? code_tool.tool_function_name
          : `${code_tool.tool_function_name}_copy`,
        tool_description: code_tool.tool_description,
        parameters_schema_string: JSON.stringify(code_tool.parameters_schema),
        code: code_tool.code,
        timeout_seconds: code_tool.timeout_seconds,
        tool_allowlist: code_tool.tool_allowlist || [],
        // Source id so the create form can stamp provenance lineage on the clone.
        clone_source_id: code_tool.id,
      },
    })
  }

  function handle_after_delete() {
    posthog.capture("delete_code_tool", {
      project_id,
      code_tool_id,
    })
    uncache_available_tools(project_id)
    goto(`/tools/${project_id}`)
  }

  function handle_after_edit() {
    fetch_code_tool()
  }

  $: detail_properties = code_tool
    ? [
        { name: "Type", value: "Code Tool" },
        { name: "Function Name", value: code_tool.tool_function_name },
        {
          name: "Model Description",
          value: code_tool.tool_description,
        },
        {
          name: "Timeout",
          value: `${code_tool.timeout_seconds}s`,
        },
        {
          name: "Created",
          value: formatDate(code_tool.created_at ?? undefined),
        },
      ]
    : []

  let code_copied = false
  function copy_code() {
    if (!code_tool) return
    navigator.clipboard
      .writeText(code_tool.code)
      .then(() => {
        code_copied = true
        setTimeout(() => (code_copied = false), 2000)
      })
      .catch((err) => {
        console.error("Failed to copy code to clipboard:", err)
      })
  }

  $: allowlist_names =
    code_tool?.tool_allowlist && code_tool.tool_allowlist.length > 0
      ? code_tool.tool_allowlist
      : null

  // Load available_tools so we can resolve allowlist IDs to friendly names
  $: if (project_id) {
    load_available_tools(project_id)
  }

  type ResolvedTool = {
    tool_id: string
    name: string
    type_label: string
    href: string | null
  }

  $: resolved_allowlist = ((): ResolvedTool[] => {
    if (!allowlist_names) return []
    const project_tools = $available_tools[project_id]
    return allowlist_names.map((tool_id) => {
      if (!project_tools) {
        return { tool_id, name: tool_id, type_label: "", href: null }
      }
      for (const tool_set of project_tools) {
        const found = tool_set.tools.find(
          (t: ToolApiDescription) => t.id === tool_id,
        )
        if (found) {
          return {
            tool_id,
            name: found.name,
            type_label: tool_set_type_label(tool_set.type as ToolSetType),
            href: tool_link(project_id, tool_id),
          }
        }
      }
      return { tool_id, name: tool_id, type_label: "", href: null }
    })
  })()
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Code Tool"
    subtitle={code_tool ? `Name: ${code_tool.name}` : ""}
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
      },
      {
        label: "Tools",
        href: `/tools/${project_id}`,
      },
    ]}
    action_buttons={code_tool
      ? [
          {
            label: "Edit",
            handler: () => edit_dialog?.show(),
          },
          {
            label: "Clone",
            handler: handle_clone,
          },
          {
            label: is_archived ? "Unarchive" : "Archive",
            handler: toggle_archive,
            loading: archive_loading,
          },
        ]
      : []}
  >
    {#if archive_error}
      <Warning
        warning_message={archive_error.getMessage() ||
          "An unknown error occurred"}
        large_icon={true}
        warning_color="error"
        outline={true}
      />
    {/if}
    {#if is_archived}
      <Warning
        warning_message="This code tool is archived. You may unarchive it to use it again."
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
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Code Tool</div>
        <div class="text-error text-sm">
          {loading_error.getMessage() || "An unknown error occurred"}
        </div>
        <button
          class="btn btn-primary mt-4"
          on:click={() => goto(`/tools/${project_id}`)}
        >
          Back to Tools
        </button>
      </div>
    {:else if code_tool}
      <div class="flex flex-col lg:flex-row gap-8 lg:gap-16">
        <!-- Left column: code, tool access, notes -->
        <div class="flex-1 min-w-0 flex flex-col gap-8">
          <div>
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xl font-bold">Code</h3>
              <button
                class="btn btn-sm btn-ghost text-gray-400 hover:text-gray-900 gap-1"
                on:click={copy_code}
                data-testid="copy-code-btn"
              >
                {#if code_copied}
                  <svg
                    class="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Copied
                {:else}
                  <svg
                    class="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path
                      d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                    />
                  </svg>
                  Copy
                {/if}
              </button>
            </div>
            <CodeEditor
              value={code_tool.code}
              readonly={true}
              min_height="300px"
            />
          </div>

          {#if allowlist_names}
            <div>
              <h3 class="text-xl font-bold mb-1">Tool Access</h3>
              <p class="text-sm text-gray-500 mb-3">
                The tools this code tool can call.
              </p>
              <div class="rounded-lg border">
                <table class="table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each resolved_allowlist as tool}
                      {#if tool.href}
                        <tr
                          class="hover:bg-base-200 cursor-pointer"
                          on:click={() => tool.href && goto(tool.href)}
                          on:keydown={(e) => {
                            if (
                              (e.key === "Enter" || e.key === " ") &&
                              tool.href
                            ) {
                              e.preventDefault()
                              goto(tool.href)
                            }
                          }}
                          role="button"
                          tabindex="0"
                        >
                          <td class="font-medium">{tool.name}</td>
                          <td class="text-sm">{tool.type_label}</td>
                        </tr>
                      {:else}
                        <tr>
                          <td class="font-mono text-sm">{tool.name}</td>
                          <td class="text-sm">{tool.type_label}</td>
                        </tr>
                      {/if}
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>
          {/if}

          {#if code_tool.description}
            <div>
              <h3 class="text-xl font-bold mb-3">Notes</h3>
              <p class="text-sm text-gray-600">{code_tool.description}</p>
            </div>
          {/if}
        </div>

        <!-- Right column: properties, test panel -->
        <div class="w-full lg:w-[420px] flex flex-col gap-6">
          <PropertyList properties={detail_properties} title="Properties" />
          <CodeToolTestPanel
            {project_id}
            tool_function_name={code_tool.tool_function_name}
            tool_description={code_tool.tool_description}
            parameters_schema={code_tool.parameters_schema}
            code={code_tool.code}
            timeout_seconds={code_tool.timeout_seconds}
            tool_allowlist={code_tool.tool_allowlist || []}
          />
        </div>
      </div>
    {:else}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Code Tool Not Found</div>
        <div class="text-gray-500 text-sm">
          The requested code tool could not be found.
        </div>
        <button
          class="btn btn-primary mt-4"
          on:click={() => goto(`/tools/${project_id}`)}
        >
          Back to Tools
        </button>
      </div>
    {/if}
  </AppPage>
</div>

{#if code_tool}
  <EditDialog
    bind:this={edit_dialog}
    name="Code Tool"
    subtitle="Only the display name can be edited. Code and parameters are immutable — use Clone to create a modified version."
    patch_url={`/api/projects/${project_id}/code_tools/${code_tool_id}`}
    delete_url={`/api/projects/${project_id}/code_tools/${code_tool_id}`}
    after_save={handle_after_edit}
    after_delete={handle_after_delete}
    fields={[
      {
        label: "Display Name",
        api_name: "name",
        value: code_tool.name,
        input_type: "input",
        description: "User-facing name for this tool.",
      },
    ]}
  />
{/if}
