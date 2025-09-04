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

  // Populate fields from parent page state if provided (only if fields are empty)
  onMount(() => {
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
  })

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

  async function connect_local_mcp() {
    try {
      error = null
      submitting = true

      const envVarsData = buildEnvVarsObject()

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/connect_local_mcp",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
            },
          },
          body: {
            name: name,
            description: description || null,
            command: command,
            args: args.trim() ? args.trim().split(/\s+/) : [], // Split into argv list; empty -> []
            env_vars: envVarsData.envVarsObj,
            secret_env_var_keys: envVarsData.secret_env_var_keys,
          },
        },
      )

      if (api_error) {
        throw api_error
      }

      if (data?.id) {
        // Delete the project_id from the available_tools, so next load it loads the updated list.
        uncache_available_tools($page.params.project_id)
        // Navigate to the tools page for the created tool
        goto(
          `/settings/manage_tools/${$page.params.project_id}/tool_servers/${data.id}`,
        )
      }
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
  <div class="max-w-4xl">
    <FormContainer
      submit_label="Connect"
      on:submit={connect_local_mcp}
      bind:error
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
                [false, "No Secret"],
                [true, "Secret"],
              ]}
              bind:value={env_vars[item_index].is_secret}
            />
          </div>
        </div>
      </FormList>
    </FormContainer>
  </div>
</div>
