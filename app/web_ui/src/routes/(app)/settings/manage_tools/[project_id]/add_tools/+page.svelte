<script lang="ts">
  import { goto } from "$app/navigation"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import SettingsItem from "$lib/ui/settings_item.svelte"
  import { client } from "$lib/api_client"

  $: project_id = $page.params.project_id

  interface RemoteMcpServer {
    name: string
    subtitle: string
    description: string
    server_url: string
    headers: { key: string; value: string; placeholder: string | null }[]
  }

  interface LocalMcpServer {
    name: string
    subtitle: string
    description: string
    command: string
    args: string[]
    env_vars: { key: string; value: string; placeholder: string | null }[]
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
      name: "Control GitHub",
      subtitle: "by GitHub",
      description: "Manage repos, issues, PRs and workflows.",
      server_url: "https://api.githubcopilot.com/mcp/",
      headers: [
        {
          key: "Authorization",
          value: "Bearer REPLACE_WITH_GITHUB_PERSONAL_ACCESS_TOKEN",
          placeholder: "Bearer REPLACE_WITH_GITHUB_PERSONAL_ACCESS_TOKEN",
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
          placeholder: "apikey REPLACE_WITH_TWELVE_DATA_API_KEY",
        },
        {
          key: "X-OpenAPI-Key",
          value: "",
          placeholder: "REPLACE_WITH_YOUR_OPENAI_API_KEY",
        },
      ],
    },
  ]

  const sampleLocalMcpServers: LocalMcpServer[] = [
    {
      name: "Web Search & Scrape",
      subtitle: "by Firecrawl",
      description: "Search the web and scrape websites.",
      command: "npx",
      args: ["-y", "firecrawl-mcp"],
      env_vars: [
        {
          key: "FIRECRAWL_API_KEY",
          value: "",
          placeholder: "REPLACE_WITH_FIRECRAWL_API_KEY",
        },
      ],
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
    },
    {
      name: "Access Files",
      subtitle: "by Anthropic",
      description:
        "Read, write, and manipulate local files through a controlled API.",
      command: "npx",
      args: [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "REPLACE_WITH_OTHER_ALLOWED_DIRECTORIES",
      ],
      env_vars: [],
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
      goto(`/settings/manage_tools/${project_id}`)
    } catch (error) {
      console.error(error)
      alert("Error enabling demo tools.")
    }
  }
</script>

<AppPage title="Add Tools">
  <div class="max-w-4xl space-y-8">
    <div class="">
      <h2 class="text-lg font-medium text-gray-900 mb-4">Example Tools</h2>
      <div
        class="carousel carousel-center max-w-full p-4 space-x-4 bg-base-200 rounded-box"
      >
        {#each sample_tools as tool}
          <div class="carousel-item">
            <div
              class="card bg-base-100 shadow-md hover:shadow-xl hover:border-primary border border-base-200 cursor-pointer transition-all duration-200 transform hover:-translate-y-1 w-48"
              on:click={tool.on_click}
              on:keydown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  tool.on_click()
                }
              }}
              tabindex="0"
              role="button"
              aria-label="Connect {tool.name}"
            >
              <div class="p-4">
                <div class="text-lg font-semibold leading-tight">
                  {tool.name}
                </div>
                {#if tool.subtitle}
                  <div class="text-xs text-gray-500 font-medium mt-1">
                    {tool.subtitle}
                  </div>
                {/if}
                <p class="text-base-content/70 text-xs leading-relaxed mt-3">
                  {tool.description}
                </p>
              </div>
            </div>
          </div>
        {/each}
      </div>
    </div>
    <div class="space-y-6">
      <SettingsHeader title="Custom Tools" />

      <div class="space-y-1">
        <SettingsItem
          name="Remote MCP Servers"
          description="Connect to remote MCP servers over the internet."
          button_text="Connect"
          on_click={() => {
            goto(`/settings/manage_tools/${project_id}/add_tools/remote_mcp`)
          }}
        />
        <SettingsItem
          name="Local MCP Servers"
          description="Connect to MCP servers you run on your machine."
          button_text="Connect"
          on_click={() => {
            goto(`/settings/manage_tools/${project_id}/add_tools/local_mcp`)
          }}
        />
      </div>
    </div>
  </div>
</AppPage>
