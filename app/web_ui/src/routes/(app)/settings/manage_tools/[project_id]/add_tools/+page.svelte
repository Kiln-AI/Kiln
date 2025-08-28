<script lang="ts">
  import { goto } from "$app/navigation"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import SettingsSection from "$lib/ui/settings_section.svelte"

  $: project_id = $page.params.project_id

  interface RemoteMcpServer {
    name: string
    description: string
    server_url: string
    headers: { key: string; value: string; placeholder: string | null }[]
    button_text: string
  }

  interface LocalMcpServer {
    name: string
    description: string
    command: string
    args: string[]
    env_vars: { key: string; value: string; placeholder: string | null }[]
    button_text: string
  }

  // Helper function to navigate to remote MCP page with pre-filled data
  function connectRemoteMcp(item: RemoteMcpServer) {
    goto(`/settings/manage_tools/${project_id}/add_tools/remote_mcp`, {
      state: {
        name: item.name,
        description: item.description,
        server_url: item.server_url,
        headers: item.headers,
      },
    })
  }

  function connectLocalMcp(item: LocalMcpServer) {
    goto(`/settings/manage_tools/${project_id}/add_tools/local_mcp`, {
      state: {
        name: item.name,
        description: item.description,
        command: item.command,
        args: item.args,
        env_vars: item.env_vars,
      },
    })
  }

  const sampleRemoteMcpServers: RemoteMcpServer[] = [
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

  const sampleLocalMcpServers: LocalMcpServer[] = [
    {
      name: "Firecrawl",
      description:
        "Firecrawl is a tool that allows you to crawl websites and extract data.",
      command: "npx",
      args: ["-y", "firecrawl-mcp"],
      env_vars: [
        {
          key: "FIRECRAWL_API_KEY",
          value: "",
          placeholder: "FIRECRAWL_API_KEY",
        },
      ],
      button_text: "Connect",
    },
    {
      name: "Filesystem",
      description:
        "Read, write, and manipulate local files through a controlled API.",
      command: "npx",
      args: [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "<Other Allowed Directories e.g. /Users/username/Desktop>",
      ],
      env_vars: [],
      button_text: "Connect",
    },
  ]
</script>

<AppPage title="Add Tools">
  <div class="max-w-4xl mt-12 space-y-12">
    <SettingsSection
      title="Sample Tools"
      items={[
        ...sampleRemoteMcpServers.map((item) => ({
          name: item.name,
          description: item.description,
          button_text: item.button_text,
          on_click: () => connectRemoteMcp(item),
        })),
        ...sampleLocalMcpServers.map((item) => ({
          name: item.name,
          description: item.description,
          button_text: item.button_text,
          on_click: () => connectLocalMcp(item),
        })),
      ]}
    />
    <SettingsSection
      title="Custom Tools"
      items={[
        {
          name: "Remote MCP Servers",
          description:
            "Connect to remote MCP servers to add tools to your project.",
          button_text: "Connect",
          on_click: () =>
            goto(`/settings/manage_tools/${project_id}/add_tools/remote_mcp`),
        },
        {
          name: "Local MCP Servers",
          description:
            "Connect to local MCP servers to add tools to your project.",
          button_text: "Connect",
          on_click: () =>
            goto(`/settings/manage_tools/${project_id}/add_tools/local_mcp`),
        },
      ]}
    />
  </div>
</AppPage>
