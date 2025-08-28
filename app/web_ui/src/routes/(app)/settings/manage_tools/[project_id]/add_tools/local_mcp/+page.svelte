<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { page } from "$app/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"

  // Environment Variables as array of key/value pairs
  interface EnvVarPair {
    key: string
    value: string
    placeholder: string | null
  }

  // Form fields
  let name = ""
  let command = ""
  let args = ""
  let env_vars: EnvVarPair[] = []
  let description = ""

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
  })

  function buildEnvVarsObject(): Record<string, string> {
    const envVarsObj: Record<string, string> = {}

    for (const envVar of env_vars) {
      if (envVar.key.trim() && envVar.value.trim()) {
        envVarsObj[envVar.key.trim()] = envVar.value.trim()
      }
    }

    return envVarsObj
  }

  async function connect_local_mcp() {
    try {
      error = null
      submitting = true

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/connect_local_mcp",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
            },
          },
          body: {
            name: name.trim(),
            description: description.trim() || null,
            command: command.trim(),
            args: args.trim().split(" "), // Split args into array of strings
            env_vars: buildEnvVarsObject(),
          },
        },
      )

      if (api_error) {
        throw api_error
      }

      if (data?.id) {
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

<AppPage
  title="Connect Local MCP Server"
  subtitle="Connect to a local Model Context Protocol (MCP) server to add external
        tools to your project."
>
  <div class="max-w-2xl">
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
        bind:value={command}
      />

      <FormElement
        label="Arguments"
        id="args"
        description="The arguments to pass to the MCP server. Each argument should be space separated."
        placeholder="run server fastmcp_quickstart stdio"
        optional={true}
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
        }}
        let:item_index
      >
        <div class="flex gap-2">
          <div class="flex-1 max-w-[200px]">
            <FormElement
              label="Environment Variable Name"
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
        </div>
      </FormList>
    </FormContainer>
  </div>
</AppPage>
