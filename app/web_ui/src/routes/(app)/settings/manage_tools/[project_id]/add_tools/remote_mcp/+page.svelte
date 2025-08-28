<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"

  // Form fields
  let name = ""
  let server_url = ""
  let description = ""

  // Headers as array of key/value pairs
  interface HeaderPair {
    key: string
    value: string
    placeholder: string | null
  }

  let headers: HeaderPair[] = []

  // Form state
  let error: KilnError | null = null
  let submitting = false

  // Populate fields from parent page state if provided (only if fields are empty)
  onMount(() => {
    if ($page.state) {
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

  function buildHeadersObject(): Record<string, string> {
    const headersObj: Record<string, string> = {}

    for (const header of headers) {
      if (header.key.trim() && header.value.trim()) {
        headersObj[header.key.trim()] = header.value.trim()
      }
    }

    return headersObj
  }

  async function connect_remote_mcp() {
    try {
      error = null
      submitting = true

      const headersObj = buildHeadersObject()

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/connect_remote_mcp",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
            },
          },
          body: {
            name: name.trim(),
            server_url: server_url.trim(),
            headers: headersObj,
            description: description.trim() || null,
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
  title="Connect Remote MCP Server"
  subtitle="Connect to a remote Model Context Protocol (MCP) server to add external
        tools to your project."
>
  <div class="max-w-2xl">
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
        </div>
      </FormList>
    </FormContainer>
  </div>
</AppPage>
