<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import ToolArgumentsList from "$lib/components/tool_arguments_list.svelte"
  import EnvironmentPresetDialog from "./environment_preset_dialog.svelte"
  import { page } from "$app/stores"
  import { tick } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import {
    load_available_tools,
    uncache_available_tools,
    ui_state,
  } from "$lib/stores"
  import type { OpenEnvServer, OpenEnvTool, NamedResetKwargs } from "$lib/types"
  import {
    OPENENV_SERVER_FIELDS,
    format_reset_arguments,
  } from "$lib/utils/openenv"
  import {
    compact_reset_arguments,
    load_openenv_server,
    load_openenv_server_tools,
    load_openenv_server_version,
    presets_without,
    save_environment_presets,
    set_openenv_server_archived,
  } from "./openenv_server_detail"
  import { agentInfo } from "$lib/agent"

  $: project_id = $page.params.project_id!
  $: openenv_server_id = $page.params.openenv_server_id!
  $: agentInfo.set({
    name: "OpenEnv Server Detail",
    description: `OpenEnv server detail for ID ${openenv_server_id} in project ID ${project_id}. Name: ${openenv_server?.name ?? "[loading]"}. Shows its server URL and version, its Environment Presets (named reset arguments), and the tools its server serves.`,
  })

  let openenv_server: OpenEnvServer | null = null
  let loading = true
  let loading_error: KilnError | null = null

  let tools: OpenEnvTool[] | null = null
  let tools_error: KilnError | null = null
  let version: string | null = null
  let version_error: KilnError | null = null

  let presets_error: KilnError | null = null
  let preset_dialog: EnvironmentPresetDialog
  // Which preset rows show their full description and reset arguments.
  let expanded: boolean[] = []

  let archive_error: KilnError | null = null
  let archive_loading = false

  let edit_dialog: EditDialog | null = null
  let edit_dialog_mounted = false

  $: if (project_id && openenv_server_id) {
    load_page(project_id, openenv_server_id)
  }

  function is_current(req_project_id: string, req_openenv_server_id: string) {
    return (
      req_project_id === project_id &&
      req_openenv_server_id === openenv_server_id
    )
  }

  async function load_page(
    req_project_id: string,
    req_openenv_server_id: string,
    show_spinner: boolean = true,
  ) {
    loading = show_spinner
    loading_error = null
    try {
      const loaded = await load_openenv_server(
        req_project_id,
        req_openenv_server_id,
      )
      if (!is_current(req_project_id, req_openenv_server_id)) return
      openenv_server = loaded
    } catch (e) {
      if (!is_current(req_project_id, req_openenv_server_id)) return
      openenv_server = null
      loading_error = createKilnError(e)
    } finally {
      if (is_current(req_project_id, req_openenv_server_id)) {
        loading = false
      }
    }
    if (openenv_server) {
      load_server_details(req_project_id, req_openenv_server_id)
    }
  }

  async function load_server_details(
    req_project_id: string,
    req_openenv_server_id: string,
  ) {
    tools = null
    tools_error = null
    version = null
    version_error = null
    const [tools_result, version_result] = await Promise.allSettled([
      load_openenv_server_tools(req_project_id, req_openenv_server_id),
      load_openenv_server_version(req_project_id, req_openenv_server_id),
    ])
    if (!is_current(req_project_id, req_openenv_server_id)) return
    if (tools_result.status === "fulfilled") {
      tools = tools_result.value
    } else {
      tools_error = createKilnError(tools_result.reason)
    }
    if (version_result.status === "fulfilled") {
      version = version_result.value
    } else {
      version_error = createKilnError(version_result.reason)
    }
  }

  async function save_presets(presets: NamedResetKwargs[]) {
    openenv_server = await save_environment_presets(
      project_id,
      openenv_server_id,
      presets,
    )
    expanded = []
  }

  async function remove_preset(index: number) {
    if (!openenv_server) return
    presets_error = null
    try {
      await save_presets(
        presets_without(openenv_server.named_reset_kwargs ?? [], index),
      )
    } catch (e) {
      presets_error = createKilnError(e)
    }
  }

  function toggle_expanded(index: number) {
    expanded[index] = !expanded[index]
  }

  async function update_archive(is_archived: boolean) {
    archive_loading = true
    archive_error = null
    try {
      openenv_server = await set_openenv_server_archived(
        project_id,
        openenv_server_id,
        is_archived,
      )
      await load_available_tools(project_id, true)
    } catch (e) {
      archive_error = createKilnError(e)
    } finally {
      archive_loading = false
    }
  }

  async function show_edit_dialog() {
    edit_dialog_mounted = true
    await tick()
    edit_dialog?.show()
  }

  function after_edit() {
    edit_dialog?.close()
    uncache_available_tools(project_id)
    load_page(project_id, openenv_server_id, false)
  }

  function properties(openenv_server: OpenEnvServer): UiProperty[] {
    const result: UiProperty[] = [
      { name: "ID", value: openenv_server.id || "Unknown" },
      { name: "Name", value: openenv_server.name || "Unknown" },
      { name: "Description", value: openenv_server.description || "N/A" },
    ]
    if (openenv_server.created_at) {
      result.push({
        name: "Created At",
        value: new Date(openenv_server.created_at).toLocaleString(),
      })
    }
    if (openenv_server.created_by) {
      result.push({ name: "Created By", value: openenv_server.created_by })
    }
    return result
  }

  function connection_properties(
    openenv_server: OpenEnvServer,
    version: string | null,
    version_error: KilnError | null,
  ): UiProperty[] {
    return [
      { name: "Type", value: "OpenEnv Server" },
      { name: "Server URL", value: openenv_server.url || "N/A" },
      version_error
        ? { name: "Version", value: "Can't reach OpenEnv server", error: true }
        : { name: "Version", value: version ?? "Loading..." },
    ]
  }

  $: presets = openenv_server?.named_reset_kwargs ?? []
  $: is_archived = openenv_server?.is_archived ?? false
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="OpenEnv Server"
    subtitle={`Name: ${openenv_server?.name || ""}`}
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
    action_buttons={openenv_server
      ? [
          { label: "Edit", handler: show_edit_dialog },
          {
            label: is_archived ? "Unarchive" : "Archive",
            handler: () => update_archive(!is_archived),
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
        warning_message="This OpenEnv server is archived. You may unarchive it to use it again."
        large_icon={true}
        warning_color="warning"
        outline={true}
      />
    {/if}
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error || !openenv_server}
      <ErrorDetailsBlock
        title="Error Loading OpenEnv Server"
        error_messages={loading_error?.getErrorMessages() ?? [
          "OpenEnv server not found.",
        ]}
      />
    {:else}
      <div class="flex flex-col lg:flex-row gap-8 lg:gap-16 mb-10">
        <div class="flex-1">
          <PropertyList
            properties={properties(openenv_server)}
            title="Properties"
          />
        </div>
        <div class="flex-1">
          <PropertyList
            properties={connection_properties(
              openenv_server,
              version,
              version_error,
            )}
            title="Connection Details"
          />
        </div>
      </div>

      <div class="flex flex-col gap-4 mb-10">
        <!-- The title's basis is the narrowest it gets beside the button. When
             both don't fit on one line, the button moves under the title. -->
        <div class="flex flex-wrap items-center gap-x-8 gap-y-4">
          <div class="grow basis-80">
            <h2 class="text-lg font-medium text-gray-900">
              Environment Presets
            </h2>
            <div class="text-sm text-gray-500">
              Named sets of reset arguments for the OpenEnv server, such as
              which company's data to load and which user the agent acts as.
              Pick one under Advanced Options on the run page.
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-3 whitespace-nowrap">
            <button
              class="btn btn-mid"
              on:click={() => preset_dialog.show_add()}
            >
              Add Environment Preset
            </button>
          </div>
        </div>
        {#if presets_error}
          <Warning
            warning_message={presets_error.getMessage() ||
              "An unknown error occurred"}
            warning_color="error"
          />
        {/if}
        {#if presets.length === 0}
          <div class="text-gray-500 rounded-lg border p-4 text-sm">
            No Environment Presets yet. Add one by clicking "Add Environment
            Preset" above.
          </div>
        {:else}
          <div class="overflow-x-auto rounded-lg border">
            <table class="table">
              <thead>
                <tr>
                  <th style="width: 25%">Name</th>
                  <th style="width: 30%">Description</th>
                  <th>Reset Arguments</th>
                  <th style="width: 40px"></th>
                </tr>
              </thead>
              <tbody>
                {#each presets as preset, index}
                  <!-- Click a row to show its full description and reset
                       arguments, as the synthetic data tables do. -->
                  <tr
                    on:click={() => toggle_expanded(index)}
                    class="cursor-pointer"
                  >
                    <td class="font-medium align-top">{preset.name}</td>
                    <td class="align-top">
                      {#if expanded[index]}
                        <div class="whitespace-pre-wrap break-words">
                          {preset.description || "None"}
                        </div>
                      {:else}
                        <div class="truncate w-0 min-w-full">
                          {preset.description || "None"}
                        </div>
                      {/if}
                    </td>
                    <td class="align-top font-mono text-sm">
                      {#if expanded[index]}
                        <pre
                          class="whitespace-pre-wrap break-words">{format_reset_arguments(
                            preset.reset_kwargs,
                          )}</pre>
                      {:else}
                        <div class="truncate w-0 min-w-full">
                          {compact_reset_arguments(preset.reset_kwargs)}
                        </div>
                      {/if}
                    </td>
                    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
                    <td class="p-0 align-top" on:click|stopPropagation>
                      <TableActionMenu
                        items={[
                          {
                            label: "Edit",
                            onclick: () => preset_dialog.show_edit(index),
                          },
                          {
                            label: "Clone",
                            onclick: () => preset_dialog.show_clone(index),
                          },
                          {
                            label: "Remove",
                            onclick: () => remove_preset(index),
                          },
                        ]}
                      />
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>

      <div class="mb-10">
        <h3 class="text-xl font-bold mb-4">Available Tools</h3>
        {#if tools_error}
          <ErrorDetailsBlock
            title="Can't Reach OpenEnv Server"
            error_messages={tools_error.getErrorMessages()}
            troubleshooting_steps={[
              "Check the OpenEnv server is running.",
              "Check the Server URL.",
            ]}
            full_width={true}
          />
        {:else if tools === null}
          <div class="w-full min-h-[20vh] flex justify-center items-center">
            <div class="loading loading-spinner loading-lg"></div>
          </div>
        {:else if tools.length > 0}
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
                {#each tools as tool}
                  <tr>
                    <td class="font-medium">{tool.name}</td>
                    <td class="max-w-[300px] whitespace-pre-line break-words"
                      >{tool.description || "None"}</td
                    >
                    <td>
                      <ToolArgumentsList input_schema={tool.input_schema} />
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <div class="text-lg mb-4 text-gray-500">
            This OpenEnv server has no tools.
          </div>
        {/if}
      </div>

      <EnvironmentPresetDialog
        bind:this={preset_dialog}
        {project_id}
        {openenv_server_id}
        {presets}
        save={save_presets}
      />
      {#if edit_dialog_mounted}
        <!-- Mounted only while open: a closed EditDialog's form still answers
             Cmd+Enter, which would re-save its stale fields when another form submits. -->
        <EditDialog
          bind:this={edit_dialog}
          name="OpenEnv Server"
          patch_url={`/api/projects/${project_id}/openenv_servers/${openenv_server_id}`}
          after_save={after_edit}
          on:close={() => (edit_dialog_mounted = false)}
          fields={[
            {
              label: OPENENV_SERVER_FIELDS.name.label,
              description: OPENENV_SERVER_FIELDS.name.description,
              api_name: "name",
              value: openenv_server.name,
              input_type: "input",
              max_length: 120,
            },
            {
              label: OPENENV_SERVER_FIELDS.description.label,
              description: OPENENV_SERVER_FIELDS.description.description,
              api_name: "description",
              value: openenv_server.description || "",
              input_type: "textarea",
              optional: true,
            },
            {
              label: OPENENV_SERVER_FIELDS.url.label,
              description: OPENENV_SERVER_FIELDS.url.description,
              placeholder: OPENENV_SERVER_FIELDS.url.placeholder,
              api_name: "url",
              value: openenv_server.url || "",
              input_type: "input",
            },
          ]}
        />
      {/if}
    {/if}
  </AppPage>
</div>
