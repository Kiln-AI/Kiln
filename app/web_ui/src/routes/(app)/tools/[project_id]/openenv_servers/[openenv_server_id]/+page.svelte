<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import ToolArgumentsList from "$lib/components/tool_arguments_list.svelte"
  import EnvironmentOptionDialog from "./environment_option_dialog.svelte"
  import { page } from "$app/stores"
  import { tick } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { uncache_available_tools, ui_state } from "$lib/stores"
  import type { OpenEnvServer, OpenEnvTool, NamedResetKwargs } from "$lib/types"
  import {
    OPENENV_SERVER_FIELDS,
    format_reset_arguments,
  } from "$lib/utils/openenv"
  import {
    load_openenv_server,
    load_openenv_server_tools,
    load_openenv_server_version,
    options_without,
    save_environment_options,
  } from "./openenv_server_detail"
  import { agentInfo } from "$lib/agent"

  $: project_id = $page.params.project_id!
  $: openenv_server_id = $page.params.openenv_server_id!
  $: agentInfo.set({
    name: "OpenEnv Detail",
    description: `OpenEnv detail for environment ID ${openenv_server_id} in project ID ${project_id}. Name: ${openenv_server?.name ?? "[loading]"}. Shows its server URL and version, its Environment Options (named reset arguments), and the tools its server serves.`,
  })

  let openenv_server: OpenEnvServer | null = null
  let loading = true
  let loading_error: KilnError | null = null

  let tools: OpenEnvTool[] | null = null
  let tools_error: KilnError | null = null
  let version: string | null = null
  let version_error: KilnError | null = null

  let options_error: KilnError | null = null
  let option_dialog: EnvironmentOptionDialog

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

  async function save_options(options: NamedResetKwargs[]) {
    openenv_server = await save_environment_options(
      project_id,
      openenv_server_id,
      options,
    )
  }

  async function remove_option(index: number) {
    if (!openenv_server) return
    options_error = null
    try {
      await save_options(
        options_without(openenv_server.named_reset_kwargs ?? [], index),
      )
    } catch (e) {
      options_error = createKilnError(e)
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
    return [
      { name: "Name", value: openenv_server.name },
      { name: "Description", value: openenv_server.description || "N/A" },
      { name: "Type", value: "OpenEnv" },
    ]
  }

  function connection_properties(
    openenv_server: OpenEnvServer,
    version: string | null,
    version_error: KilnError | null,
  ): UiProperty[] {
    return [
      { name: "Server URL", value: openenv_server.url || "N/A" },
      version_error
        ? { name: "Version", value: "Can't reach OpenEnv", error: true }
        : { name: "Version", value: version ?? "Loading..." },
    ]
  }

  $: options = openenv_server?.named_reset_kwargs ?? []
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="OpenEnv"
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
      ? [{ label: "Edit", handler: show_edit_dialog }]
      : []}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error || !openenv_server}
      <ErrorDetailsBlock
        title="Error Loading OpenEnv"
        error_messages={loading_error?.getErrorMessages() ?? [
          "OpenEnv not found.",
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
              Environment Options
            </h2>
            <div class="text-sm text-gray-500">
              The reset options sent to the OpenEnv, saved under a name, such as
              which company's data to load and which user the agent acts as.
              Pick one from Environment Options on the run page.
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-3 whitespace-nowrap">
            <button
              class="btn btn-mid"
              on:click={() => option_dialog.show_add()}
            >
              Add Environment Option
            </button>
          </div>
        </div>
        {#if options_error}
          <Warning
            warning_message={options_error.getMessage() ||
              "An unknown error occurred"}
            warning_color="error"
          />
        {/if}
        {#if options.length === 0}
          <div class="text-gray-500 rounded-lg border p-4 text-sm">
            No Environment Options yet. Add one by clicking "Add OpenEnv Option"
            above.
          </div>
        {:else}
          <div class="overflow-x-auto rounded-lg border">
            <table class="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Reset Arguments</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {#each options as option, index}
                  <tr>
                    <td class="font-medium align-top">{option.name}</td>
                    <td class="font-mono text-sm whitespace-pre"
                      >{format_reset_arguments(option.reset_kwargs)}</td
                    >
                    <td class="p-0 align-top">
                      <TableActionMenu
                        items={[
                          {
                            label: "Edit",
                            onclick: () => option_dialog.show_edit(index),
                          },
                          {
                            label: "Clone",
                            onclick: () => option_dialog.show_clone(index),
                          },
                          {
                            label: "Remove",
                            onclick: () => remove_option(index),
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
            title="Can't Reach OpenEnv"
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
            This OpenEnv has no tools.
          </div>
        {/if}
      </div>

      <EnvironmentOptionDialog
        bind:this={option_dialog}
        {options}
        save={save_options}
      />
      {#if edit_dialog_mounted}
        <!-- Mounted only while open: a closed EditDialog's form still answers
             Cmd+Enter, which would re-save its stale fields when another form submits. -->
        <EditDialog
          bind:this={edit_dialog}
          name="OpenEnv"
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
              info_description: OPENENV_SERVER_FIELDS.url.info_description,
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
