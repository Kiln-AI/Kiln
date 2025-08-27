<script lang="ts">
  import { goto } from "$app/navigation"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import SettingsItem from "$lib/ui/settings_item.svelte"

  $: project_id = $page.params.project_id

  // Type definition for MCP tool items
  interface McpServer {
    name: string
    description: string
    server_url: string
    headers: { key: string; value: string; placeholder: string | null }[]
    button_text: string
  }

  // Helper function to navigate to remote MCP page with pre-filled data
  function connectRemoteMcp(item: McpServer) {
    goto(`/settings/manage_tools/${project_id}/add_tools/remote_mcp`, {
      state: {
        name: item.name,
        description: item.description,
        server_url: item.server_url,
        headers: item.headers,
      },
    })
  }

  const sampleMcpServers: McpServer[] = [
    {
      name: "GitHub",
      description:
        "Adds ability to read repositories and code files, manage issues and PRs, analyze code, and automate workflow.",
      server_url: "https://api.githubcopilot.com/mcp/",
      headers: [
        {
          key: "Authorization",
          value: "Bearer REPLACE_WITH_GITHUB_PERSONAL_ACCESS_TOKEN",
          placeholder: "Bearer REPLACE_WITH_GITHUB_PERSONAL_ACCESS_TOKEN",
        },
      ],
      button_text: "Connect",
    },
    {
      name: "Twelve Data",
      description:
        "Integrates with Twelve Data API to provide real-time quotes, historical OHLCV price data, and instrument metadata for stocks, forex pairs, and cryptocurrencies across global markets.",
      server_url: "https://mcp.twelvedata.com/mcp/",
      headers: [
        {
          key: "Authorization",
          value: "apikey REPLACE_WITH_TWELVE_DATA_API_KEY",
          placeholder: "apikey REPLACE_WITH_TWELVE_DATA_API_KEY",
        },
        {
          key: "X-OpenAPI-Key",
          value: "",
          placeholder: "REPLACE_WITH_YOUR_OPENAI_API_KEY",
        },
      ],
      button_text: "Connect",
    },
    {
      name: "Postman Echo",
      description: "Simple MCP Server to test MCP tool connections.",
      server_url: "https://postman-echo-mcp.fly.dev/",
      headers: [],
      button_text: "Connect",
    },
  ]

  let sections = [
    {
      category: "Sample Tools",
      items: [
        // TODO: Add more custom tool servers, pre-filled in.
        ...sampleMcpServers.map((tool) => ({
          ...tool,
          on_click: () => connectRemoteMcp(tool),
        })),
      ],
    },
    {
      category: "Custom Tools",
      items: [
        {
          name: "Remote MCP Servers",
          description:
            "Connect to remote MCP servers to add tools to your project.",
          button_text: "Connect",
          on_click: () => {
            goto(`/settings/manage_tools/${project_id}/add_tools/remote_mcp`)
          },
        },
        {
          name: "Local MCP Servers",
          description:
            "Connect to local MCP servers to add tools to your project.",
          button_text: "Connect",
          on_click: () => {
            goto(`/settings/manage_tools/${project_id}/add_tools/local_mcp`)
          },
        },
      ],
    },
  ]
</script>

<AppPage title="Add Tools">
  <div class="max-w-4xl mt-12 space-y-12">
    {#each sections as section}
      <div class="space-y-6">
        <SettingsHeader title={section.category} />

        <div class="space-y-1">
          {#each section.items as item}
            <SettingsItem
              name={item.name}
              description={item.description}
              button_text={item.button_text}
              on_click={item.on_click}
            />
          {/each}
        </div>
      </div>
    {/each}
  </div>
</AppPage>
