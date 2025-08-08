<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  $: project_id = $page.params.project_id

  // Form fields
  let name = ""
  let server_url = ""
  let description = ""

  // Headers as array of key/value pairs
  interface HeaderPair {
    key: string
    value: string
  }

  let headers: HeaderPair[] = [{ key: "", value: "" }]

  // Form state
  let error: KilnError | null = null
  let submitting = false

  function addHeader() {
    headers = [...headers, { key: "", value: "" }]
  }

  function removeHeader(index: number) {
    if (headers.length > 1) {
      headers = headers.filter((_, i) => i !== index)
    }
  }

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

      const headersObj = buildHeadersObject()

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/connect_remote_MCP",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name.trim(),
            server_url: server_url.trim(),
            headers: headersObj as unknown as Record<string, never>, // Type assertion to work around schema issue
            description: description.trim() || null,
          },
        },
      )

      if (api_error) {
        throw api_error
      }

      if (data?.id) {
        // Navigate to the tools page for the created tool
        goto(`/settings/manage_tools/${project_id}/tools/${data.id}`)
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<AppPage title="Add Tools">
  <div class="max-w-2xl">
    <div class="mb-6">
      <h2 class="text-xl font-semibold mb-2">Connect Remote MCP Server</h2>
      <p class="text-sm text-gray-600">
        Connect to a remote Model Context Protocol (MCP) server to add external
        tools to your project.
      </p>
    </div>

    <FormContainer
      submit_label="Connect Remote MCP"
      on:submit={connect_remote_mcp}
      bind:error
      bind:submitting
    >
      <FormElement label="Name" id="name" bind:value={name} max_length={120} />

      <FormElement
        label="Server URL"
        id="mcp_server_url"
        description="The URL of the remote MCP server"
        placeholder="https://example.com/mcp"
        bind:value={server_url}
      />

      <!-- Headers section -->
      <FormElement
        inputType="header_only"
        label="Headers"
        id="headers"
        description="Add authentication headers or other required headers for the MCP server"
        optional={true}
        bind:value={headers}
      />

      <div class="space-y-3">
        {#each headers as header, index}
          <div class="flex gap-2 items-center">
            <input
              type="text"
              placeholder="Header name (e.g., Authorization)"
              class="input input-bordered flex-1"
              bind:value={header.key}
            />
            <input
              type="text"
              placeholder="Header value (e.g., Bearer token-here)"
              class="input input-bordered flex-1"
              bind:value={header.value}
            />
            <button
              type="button"
              class="btn btn-error btn-sm"
              on:click={() => removeHeader(index)}
              disabled={headers.length === 1}
              aria-label="Remove header"
            >
              ✕
            </button>
          </div>
        {/each}

        <button
          type="button"
          class="btn btn-outline btn-sm"
          on:click={addHeader}
        >
          + Add Header
        </button>
      </div>

      <FormElement
        label="Description"
        inputType="textarea"
        id="mcp_description"
        description="Optional description of what this tool does"
        optional={true}
        bind:value={description}
      />
    </FormContainer>
  </div>
</AppPage>
