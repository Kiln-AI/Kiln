<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import type { McpServerKeyValuePair } from "$lib/tools"
  import { uncache_available_tools } from "$lib/stores"
  import type { ExternalToolServerApiDescription } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import posthog from "posthog-js"

  // The existing tool server, if we're editing
  export let editing_tool_server: ExternalToolServerApiDescription | null = null
  let editing_requires_secrets: boolean = false

  // Form fields
  let name = ""
  let server_url = ""
  let description = ""

  let headers: McpServerKeyValuePair[] = []

  // Form state
  let error: KilnError | null = null
  let submitting = false

  // Populate fields from parent page state if provided (only if fields are empty)
  onMount(async () => {
    if (editing_tool_server) {
      load_existing_tool_server()
    } else if ($page.state) {
      const state = $page.state || {}
      if ("name" in state && typeof state["name"] === "string") {
        name = state.name
      }
      if ("description" in state && typeof state["description"] === "string") {
        description = state.description
      }
      if ("server_url" in state && typeof state["server_url"] === "string") {
        server_url = state.server_url
      }
      if ("headers" in state && Array.isArray(state.headers)) {
        headers = [...state.headers]
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

    if (props.server_url && typeof props.server_url === "string") {
      server_url = props.server_url
    }

    if (props.headers && typeof props.headers === "object") {
      for (const [key, value] of Object.entries(props.headers)) {
        if (typeof key === "string" && typeof value === "string") {
          headers.push({
            key: key,
            value: value,
            is_secret: false,
            placeholder: "",
          })
        } else {
          error = new KilnError(
            "Invalid header key or value when loading existing tool server",
            null,
          )
          return
        }
      }
      // For svelte reactivity, we need to set the headers array
      headers = headers
    }

    if (props.secret_header_keys && Array.isArray(props.secret_header_keys)) {
      for (const key of props.secret_header_keys) {
        headers.push({
          key: key,
          value: "SECRET_VALUE",
          is_secret: true,
          placeholder: "",
        })
        editing_requires_secrets = true
      }
      // For svelte reactivity, we need to set the headers array
      headers = headers
    }
  }

  function buildHeadersObject(): {
    headersObj: Record<string, string>
    secret_header_keys: string[]
  } {
    const headersObj: Record<string, string> = {}
    const secretHeaderKeys: string[] = []

    for (const header of headers) {
      if (header.key.trim() && header.value.trim()) {
        const key = header.key
        headersObj[key] = header.value

        if (header.is_secret) {
          secretHeaderKeys.push(key)
        }
      }
    }

    return {
      headersObj: headersObj,
      secret_header_keys: secretHeaderKeys,
    }
  }

  async function connect_remote_mcp() {
    // Check if secrets are missing and need to be set
    if (editing_requires_secrets) {
      for (const header of headers) {
        if (header.is_secret && header.value.includes("SECRET_VALUE")) {
          error = new KilnError(
            "Please enter the value for the secret headers anywhere it says 'SECRET_VALUE'.",
            null,
          )
          submitting = false
          return
        }
      }
    }

    try {
      error = null
      submitting = true

      const headersData = buildHeadersObject()

      const body = {
        name: name,
        server_url: server_url,
        headers: headersData.headersObj,
        secret_header_keys: headersData.secret_header_keys,
        description: description || null,
      }

      let server_id: string | null | undefined = undefined
      let api_error = null

      if (editing_tool_server) {
        const { data, error: resp_error } = await client.PATCH(
          "/api/projects/{project_id}/edit_remote_mcp/{tool_server_id}",
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
        api_error = resp_error
      } else {
        const { data, error: resp_error } = await client.POST(
          "/api/projects/{project_id}/connect_remote_mcp",
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
        api_error = resp_error
      }

      if (api_error) {
        throw api_error
      }
      if (!server_id) {
        throw new Error("Failed to get server id")
      }

      if (editing_requires_secrets) {
        posthog.capture("edit_remote_mcp", {})
      } else {
        posthog.capture("connect_remote_mcp", {})
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
      submit_label="Connect"
      on:submit={connect_remote_mcp}
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
        label="Server URL"
        id="mcp_server_url"
        description="The URL of the remote MCP server."
        placeholder="https://example.com/mcp"
        bind:value={server_url}
      />

      <!-- Headers section -->
      <FormElement
        inputType="header_only"
        label="Headers"
        id="headers_section"
        description="If the documentation for the server you're adding requires custom headers, enter them here."
        info_description="Some MCP servers require custom headers, such as the 'Authorization' headers. Refer to the documentation for the server you're adding to see if they require headers."
        value=""
      />

      <FormList
        content={headers}
        content_label="Header"
        start_with_one={false}
        empty_description="No Headers"
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
              label="Header Name"
              id="header_name_{item_index}"
              info_description="The HTTP header name, such as 'Authorization'"
              placeholder="Header name"
              light_label={true}
              bind:value={headers[item_index].key}
            />
          </div>
          <div class="flex-1">
            <FormElement
              label="Value"
              id="header_value_{item_index}"
              info_description="The header value, such as 'Bearer your-token-here'"
              placeholder={headers[item_index].placeholder || "Value"}
              light_label={true}
              bind:value={headers[item_index].value}
            />
          </div>
          <div class="flex-1 max-w-[140px]">
            <FormElement
              inputType="select"
              label="Secret"
              id="secret_{item_index}"
              info_description="If this header is a secret such as an API key, select 'Secret' to prevent it from being synced. Kiln will store the secret in your project's settings."
              light_label={true}
              select_options={[
                [false, "Not Secret"],
                [true, "Secret"],
              ]}
              bind:value={headers[item_index].is_secret}
            />
          </div>
        </div>
      </FormList>
    </FormContainer>
  </div>
</div>
