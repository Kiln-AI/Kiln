<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
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
        "/api/projects/{project_id}/connect_remote_MCP",
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
          `/settings/manage_tools/${$page.params.project_id}/tools/${data.id}`,
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
      <FormElement label="Name" id="name" bind:value={name} max_length={120} />

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
        description="The URL of the remote MCP server"
        placeholder="https://example.com/mcp"
        bind:value={server_url}
      />

      <!-- Headers section -->
      <div class="text-sm font-medium text-left flex flex-col gap-1 w-full">
        <div class="flex flex-row items-center">
          <span class="grow">Headers</span>
        </div>
        <div class="text-xs text-gray-500">
          Add authentication headers or other required headers for the MCP
          server.
        </div>
      </div>

      <FormList
        content={headers}
        content_label="Header"
        start_with_one={false}
        empty_content={{
          key: "",
          value: "",
        }}
        let:item_index
      >
        <div class="flex gap-2">
          <div class="flex-1">
            <label
              class="text-sm font-medium text-left flex flex-col gap-1 w-full"
            >
              <div class="flex flex-row items-center">
                <span class="grow text-xs text-gray-500 h-4">Header Name</span>
                <div class="text-gray-500 h-4 mt-[-4px]">
                  <InfoTooltip
                    tooltip_text="The HTTP header name, such as 'Authorization'"
                  />
                </div>
              </div>
              <input
                type="text"
                placeholder="Header name"
                class="input input-bordered"
                bind:value={headers[item_index].key}
              />
            </label>
          </div>
          <div class="flex-1">
            <label
              class="text-sm font-medium text-left flex flex-col gap-1 w-full"
            >
              <div class="flex flex-row items-center">
                <span class="grow text-xs text-gray-500 h-4">Value</span>
                <div class="text-gray-500 h-4 mt-[-4px]">
                  <InfoTooltip
                    tooltip_text="The header value, such as 'Bearer your-token-here'"
                  />
                </div>
              </div>
              <input
                type="text"
                placeholder="Value"
                class="input input-bordered"
                bind:value={headers[item_index].value}
              />
            </label>
          </div>
        </div>
      </FormList>
    </FormContainer>
  </div>
</AppPage>
