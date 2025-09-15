<script lang="ts">
  import { goto } from "$app/navigation"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import SettingsSection from "$lib/ui/settings_section.svelte"
  import { client } from "$lib/api_client"
  import type { McpServerKeyValuePair } from "$lib/tools"
  import { uncache_available_tools } from "$lib/stores"
  import FeatureCarousel from "$lib/ui/feature_carousel.svelte"

  $: project_id = $page.params.project_id

  type BaseMcpServer = {
    name: string
    subtitle: string
    description: string
  }

  type RemoteMcpServer = BaseMcpServer & {
    server_url: string
    headers: McpServerKeyValuePair[]
  }

  type LocalMcpServer = BaseMcpServer & {
    command: string
    args: string[]
    env_vars: McpServerKeyValuePair[]
    installation_instruction: string
  }

  // Helper function to navigate to remote MCP page with pre-filled data
  function connectRemoteMcp(item: RemoteMcpServer) {
    goto(`/settings/manage_tools/${project_id}/add_tools/remote_mcp`, {
      state: {
        name: item.name + " " + item.subtitle,
        description: item.description,
        server_url: item.server_url,
        headers: item.headers,
      },
    })
  }

  function connectLocalMcp(item: LocalMcpServer) {
    goto(`/settings/manage_tools/${project_id}/add_tools/local_mcp`, {
      state: {
        name: item.name + " " + item.subtitle,
        description: item.description,
        command: item.command,
        args: item.args,
        env_vars: item.env_vars,
        installation_instruction: item.installation_instruction,
      },
    })
  }

  const sampleRemoteMcpServers: RemoteMcpServer[] = [
    {
      name: "Control GitHub",
      subtitle: "by GitHub",
      description: "Manage repos, issues, PRs and workflows.",
      server_url: "https://api.githubcopilot.com/mcp/",
      headers: [
        {
          key: "Authorization",
          value: "Bearer REPLACE_WITH_GITHUB_PERSONAL_ACCESS_TOKEN",
          placeholder: "Format: 'Bearer your-token-here'",
          is_secret: true,
        },
      ],
    },
    {
      name: "Stock Quotes",
      subtitle: "by Twelve Data",
      description: "Real-time quotes and historical data.",
      server_url: "https://mcp.twelvedata.com/mcp/",
      headers: [
        {
          key: "Authorization",
          value: "apikey REPLACE_WITH_TWELVE_DATA_API_KEY",
          placeholder: "Format: 'apikey your-api-key-here'",
          is_secret: true,
        },
        {
          key: "X-OpenAPI-Key",
          value: "",
          placeholder: "Your OpenAI API Key",
          is_secret: true,
        },
      ],
    },
  ]

  const sampleLocalMcpServers: LocalMcpServer[] = [
    {
      name: "Web Search & Scrape",
      subtitle: "by Firecrawl",
      description: "Search the web and scrape websites into text.",
      command: "npx",
      args: ["-y", "firecrawl-mcp"],
      env_vars: [
        {
          key: "FIRECRAWL_API_KEY",
          value: "",
          placeholder: "Your Firecrawl API Key",
          is_secret: true,
        },
      ],
      installation_instruction:
        "You must have Node.js installed: https://nodejs.org. If you had to install node, restart Kiln before connecting the server.",
    },
    {
      name: "Run Python Code",
      subtitle: "by Pydantic",
      description: "Run Python code in a sandboxed environment.",
      command: "deno",
      args: [
        "run",
        "-N",
        "-R=node_modules",
        "-W=node_modules",
        "--node-modules-dir=auto",
        "jsr:@pydantic/mcp-run-python",
        "stdio",
      ],
      env_vars: [],
      installation_instruction:
        "You must have deno, a JavaScript runtime, installed: https://deno.com. If you had to install deno, restart Kiln before connecting the server.",
    },
    {
      name: "Access Files",
      subtitle: "by Anthropic",
      description: "Read, write, and manipulate local files on your machine.",
      command: "npx",
      args: [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "REPLACE_WITH_LIST_OF_ALLOWED_DIRECTORIES",
      ],
      env_vars: [],
      installation_instruction:
        "You must have Node.js installed: https://nodejs.org. If you had to install node, restart Kiln before connecting the server.",
    },
  ]

  const sample_tools = [
    {
      name: "Math Tools",
      subtitle: "by Kiln",
      description:
        "One click to try out tool calling, for simple math operations.",
      button_text: "Enable",
      on_click: () => enable_demo_tools(),
    },
    ...sampleLocalMcpServers.map((tool) => ({
      ...tool,
      on_click: () => connectLocalMcp(tool),
    })),
    ...sampleRemoteMcpServers.map((tool) => ({
      ...tool,
      on_click: () => connectRemoteMcp(tool),
    })),
  ]

  async function enable_demo_tools() {
    try {
      const { error } = await client.POST("/api/demo_tools", {
        params: {
          query: {
            enable_demo_tools: true,
          },
        },
      })
      if (error) {
        throw error
      }
      // Delete the project_id from the available_tools, so next load it loads the updated list.
      uncache_available_tools(project_id)
      goto(`/settings/manage_tools/${project_id}`)
    } catch (error) {
      console.error(error)
      alert("Error enabling demo tools.")
    }
  }
</script>

<AppPage
  title="Add Tools"
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/tools-and-mcp#connecting-tools"
  breadcrumbs={[
    {
      label: "Settings",
      href: `/settings`,
    },
    {
      label: "Manage Tools",
      href: `/settings/manage_tools/${project_id}`,
    },
  ]}
>
  <div>
    <h2 class="text-lg font-medium text-gray-900 mb-3">Example Tools</h2>
    <FeatureCarousel features={sample_tools} />
    <div class="max-w-4xl mt-8">
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
  </div>
</AppPage>
