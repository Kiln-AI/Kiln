<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  // Form fields
  let name = ""
  let server_url = ""
  let description = ""

  // Headers as array of key/value pairs
  interface HeaderPair {
    key: string
    value: string
  }

  let headers: HeaderPair[] = []

  // Form state
  let error: KilnError | null = null
  let submitting = false

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

      // Validate required fields
      if (!name.trim()) {
        throw new Error("Name is required")
      }
      if (!server_url.trim()) {
        throw new Error("Server URL is required")
      }
      if (headers.length > 0) {
        for (const header of headers) {
          if (!header.key.trim()) {
            throw new Error("Header name is required")
          }
          if (!header.value.trim()) {
            throw new Error("Header value is required")
          }
        }
      }

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
  sub_subtitle="Connect to a remote Model Context Protocol (MCP) server to add external
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
        info_description="These are usually not needed. Some MCP servers require custom headers, such as the 'Authorization' headers. Refer to the documentation for the server you're adding to see if they require headers."
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
          <div class="flex-1">
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
              placeholder="Value"
              light_label={true}
              bind:value={headers[item_index].value}
            />
          </div>
        </div>
      </FormList>
    </FormContainer>
  </div>
</AppPage>
