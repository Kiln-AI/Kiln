<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { page } from "$app/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { McpServerKeyValuePair } from "$lib/tools"
  import { uncache_available_tools } from "$lib/stores"
  import type { ExternalToolServerApiDescription } from "$lib/types"
  import posthog from "posthog-js"
  import { view_logs } from "$lib/utils/logs"
  import Output from "../../../../../run/output.svelte"

  // The existing tool server, if we're editing
  export let editing_tool_server: ExternalToolServerApiDescription | null = null
  let editing_requires_secrets: boolean = false

  // Form fields
  let name = ""
  let command = ""
  let args = ""
  let env_vars: McpServerKeyValuePair[] = []
  let description = ""
  let installation_instruction = ""
  // Form state
  let error: KilnError | null = null
  let submitting = false

  // Populate fields from the existing server or page state if provided (only if fields are empty)
  onMount(() => {
    if (editing_tool_server) {
      load_existing_tool_server()
    } else {
      // Try to load from page state (examples)
      const state = $page.state || {}
      if ("name" in state && typeof state["name"] === "string") {
        name = state.name
      }
      if ("description" in state && typeof state["description"] === "string") {
        description = state.description
      }
      if ("command" in state && typeof state["command"] === "string") {
        command = state.command
      }
      if ("args" in state && Array.isArray(state["args"])) {
        args = state.args.join(" ")
      }
      if ("env_vars" in state && Array.isArray(state["env_vars"])) {
        env_vars = [...state.env_vars]
      }
      if (
        "installation_instruction" in state &&
        typeof state["installation_instruction"] === "string"
      ) {
        installation_instruction = state.installation_instruction
      }
    }
  })

  function load_existing_tool_server() {
    if (!editing_tool_server) {
      return
    }
    name = editing_tool_server.name
    description = editing_tool_server.description || ""

    // We should fix the server type, so it's not "never" and we don't need a cast
    const props = editing_tool_server.properties as Record<string, unknown>

    if (props.command && typeof props.command === "string") {
      command = props.command
    }

    let api_args = props.args
    if (api_args && Array.isArray(api_args)) {
      args = api_args.join(" ")
    }

    // Load the non-secret env vars to the form
    let api_env_vars = props.env_vars
    if (api_env_vars && typeof api_env_vars === "object") {
      for (const [key, value] of Object.entries(api_env_vars)) {
        if (typeof key === "string" && typeof value === "string") {
          env_vars.push({
            key: key,
            value: value,
            is_secret: false,
            placeholder: "",
          })
        } else {
          error = new KilnError(
            "Invalid env var key or value when loading existing tool server",
            null,
          )
          return
        }
      }
      // For svelte reactivity, we need to set the env_vars array
      env_vars = env_vars
    }

    // Load the secret env vars to the form
    let api_secret_env_vars = props.secret_env_var_keys
    if (api_secret_env_vars && Array.isArray(api_secret_env_vars)) {
      for (const key of api_secret_env_vars) {
        env_vars.push({
          key: key,
          value: "SECRET_VALUE",
          is_secret: true,
          placeholder: "",
        })
        editing_requires_secrets = true
      }
      // For svelte reactivity, we need to set the env_vars array
      env_vars = env_vars
    }
  }
  function buildEnvVarsObject(): {
    envVarsObj: Record<string, string>
    secret_env_var_keys: string[]
  } {
    const envVarsObj: Record<string, string> = {}
    const secretEnvVarKeys: string[] = []

    for (const envVar of env_vars) {
      if (envVar.key.trim() && envVar.value.trim()) {
        const key = envVar.key
        envVarsObj[key] = envVar.value

        if (envVar.is_secret) {
          secretEnvVarKeys.push(key)
        }
      }
    }

    return {
      envVarsObj: envVarsObj,
      secret_env_var_keys: secretEnvVarKeys,
    }
  }

  async function save_or_connect() {
    if (editing_tool_server) {
      await save_local_mcp()
    } else {
      await connect_local_mcp()
    }
  }

  async function save_local_mcp() {
    // Check if any of the secret env vars are unset
    for (const envVar of env_vars) {
      if (envVar.is_secret && envVar.value.includes("SECRET_VALUE")) {
        error = new KilnError(
          "Please enter the value for the secret environment variables anywhere it says 'SECRET_VALUE'.",
          null,
        )
        submitting = false
        return
      }
    }

    await connect_local_mcp()
  }

  async function connect_local_mcp() {
    try {
      error = null
      submitting = true

      const envVarsData = buildEnvVarsObject()

      const body = {
        name: name,
        description: description || null,
        command: command,
        args: args.trim() ? args.trim().split(/\s+/) : [], // Split into argv list; empty -> []
        env_vars: envVarsData.envVarsObj,
        secret_env_var_keys: envVarsData.secret_env_var_keys,
      }

      let server_id: string | null | undefined = undefined
      let api_error = null

      if (editing_tool_server) {
        const { data, error } = await client.PATCH(
          "/api/projects/{project_id}/edit_local_mcp/{tool_server_id}",
          {
            params: {
              path: {
                project_id: $page.params.project_id,
                tool_server_id: editing_tool_server.id || "",
              },
            },
            body: body,
          },
        )
        server_id = data?.id
        api_error = error
      } else {
        const { data, error } = await client.POST(
          "/api/projects/{project_id}/connect_local_mcp",
          {
            params: {
              path: {
                project_id: $page.params.project_id,
              },
            },
            body: body,
          },
        )
        server_id = data?.id
        api_error = error
      }

      if (api_error) {
        throw api_error
      }
      if (!server_id) {
        throw new Error("Failed to get server id")
      }

      if (editing_tool_server) {
        posthog.capture("edit_local_mcp", {})
      } else {
        posthog.capture("connect_local_mcp", {})
      }

      // Delete the project_id from the available_tools, so next load it loads the updated list.
      uncache_available_tools($page.params.project_id)
      // Navigate to the tools page for the created tool
      goto(
        `/settings/manage_tools/${$page.params.project_id}/tool_servers/${server_id}`,
      )
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<div>
  {#if installation_instruction}
    <div class="mb-6">
      <Warning
        warning_color="warning"
        warning_icon="info"
        large_icon={true}
        warning_message={installation_instruction}
      />
    </div>
  {/if}
  {#if editing_requires_secrets}
    <div class="mb-6 max-w-lg">
      <Warning
        warning_message="This server requires secrets, such as API keys. You must enter them below wherever it says 'SECRET_VALUE' to edit this server."
        large_icon={true}
      />
    </div>
  {/if}
  <div class="max-w-4xl">
    <FormContainer
      submit_label={editing_tool_server ? "Save" : "Connect"}
      on:submit={save_or_connect}
      bind:submitting
    >
      <FormElement
        label="Name"
        id="name"
        description="A name to identify this MCP server."
        bind:value={name}
        max_length={120}
      />

      <FormElement
        label="Description"
        inputType="textarea"
        id="mcp_description"
        description="A description of this MCP server for your reference."
        optional={true}
        bind:value={description}
      />

      <FormElement
        label="Command"
        id="command"
        description="The command to run the MCP server."
        placeholder="uv, python, npx etc."
        info_description="The program used to start the MCP server (e.g. 'npx', 'python', 'uv', 'npm')."
        bind:value={command}
      />

      <FormElement
        label="Arguments"
        id="args"
        description="A list of arguments to pass to the MCP server."
        placeholder="run server fastmcp_quickstart stdio"
        info_description="Extra instructions after the command that control what or how it runs (e.g. 'firecrawl-mcp -y stdio', 'myserver.py stdio', 'run my-mcp-server --port 8080')."
        optional={true}
        inputType="textarea"
        bind:value={args}
      />

      <!-- Environment Variables section -->
      <FormElement
        inputType="header_only"
        label="Environment Variables"
        id="env_vars_section"
        description="If the documentation for the server you're adding requires custom environment variables, enter them here."
        info_description="These are usually not needed. Some MCP servers require custom environment variables, such as the API Key. Refer to the documentation for the server you're adding to see if they require environment variables."
        value=""
      />

      <FormList
        content={env_vars}
        content_label="Environment Variable"
        start_with_one={false}
        empty_description="No Environment Variables"
        empty_content={{
          key: "",
          value: "",
          is_secret: false,
        }}
        let:item_index
      >
        <div class="flex gap-2">
          <div class="flex-1 max-w-[200px]">
            <FormElement
              label="Name"
              id="env_var_name_{item_index}"
              info_description="The name of the environment variable, such as 'API_KEY'"
              placeholder="Name"
              light_label={true}
              bind:value={env_vars[item_index].key}
            />
          </div>
          <div class="flex-1">
            <FormElement
              label="Value"
              id="env_var_value_{item_index}"
              info_description="The value of the environment variable, such as 'your-api-key-here'"
              placeholder={env_vars[item_index].placeholder || "Value"}
              light_label={true}
              bind:value={env_vars[item_index].value}
            />
          </div>
          <div class="flex-1 max-w-[140px]">
            <FormElement
              inputType="select"
              label="Secret"
              id="secret_{item_index}"
              info_description="If this environment variable is a secret such as an API key, select 'Secret' to prevent it from being synced. Kiln will store the secret in your project's settings."
              light_label={true}
              select_options={[
                [false, "Not Secret"],
                [true, "Secret"],
              ]}
              bind:value={env_vars[item_index].is_secret}
            />
          </div>
        </div>
      </FormList>

      {#if error}
        <div
          class="mb-6 flex flex-col gap-4 max-w-[600px] mx-auto border p-4 rounded-md"
        >
          <span class="font-bold text-error"
            >Could Not Connect to MCP Server</span
          >

          <div class="flex flex-col gap-2">
            <span class="font-medium">Troubleshooting Steps</span>
            <ol
              class="text-sm list-decimal list-outside pl-6 flex flex-col gap-2"
            >
              <li>
                Check the Error Details below for information about the issue.
              </li>
              <li>
                Check the server's documentation for the correct setup
                (dependencies, etc.).
              </li>
              <li>
                Ensure your command <span
                  class="font-mono text-xs font-bold bg-base-200 p-1 rounded-sm"
                  >{command}
                  {args}</span
                > runs in your terminal. If you had to install libraries or dependencies,
                restart the Kiln app before trying again.
              </li>
              <li>
                Check Kiln logs for additional details. <button
                  type="button"
                  class="link"
                  on:click={view_logs}
                >
                  View Logs
                </button>
              </li>
            </ol>
          </div>
          <div class="flex flex-col gap-2">
            <span class="font-medium">Error Details</span>
            <Output
              raw_output={error.getErrorMessages().join("\n\n")}
              hide_toggle={false}
              max_height="120px"
            />
          </div>
        </div>
      {/if}
    </FormContainer>
  </div>
</div>
