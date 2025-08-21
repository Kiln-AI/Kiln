<script lang="ts">
  import { goto } from "$app/navigation"
  import AppPage from "../../../../app_page.svelte"
  import { ui_state } from "$lib/stores"

  // Type definition for MCP tool items
  interface McpServer {
    name: string
    description: string
    server_url: string
    headers: { key: string; value: string }[]
    button_text: string
  }

  // Helper function to navigate to remote MCP page with pre-filled data
  function connectRemoteMcp(item: McpServer) {
    goto(
      `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/remote_mcp`,
      {
        state: {
          name: item.name,
          description: item.description,
          server_url: item.server_url,
          headers: item.headers,
        },
      },
    )
  }

  const sampleMcpServers: McpServer[] = [
    {
      name: "Firecrawl",
      description: "Add Firecrawl to your project to search the web.",
      server_url: "https://firecrawl.com",
      headers: [{ key: "Authorization", value: "" }],
      button_text: "Connect",
    },
    {
      name: "Perplexity",
      description: "Add Perplexity to your project to search the web.",
      server_url: "https://api.perplexity.ai",
      headers: [{ key: "Authorization", value: "" }],
      button_text: "Connect",
    },
    {
      name: "GitHub",
      description:
        "Adds ability to read repositories and code files, manage issues and PRs, analyze code, and automate workflow.",
      server_url: "https://api.githubcopilot.com/mcp/",
      headers: [{ key: "Authorization", value: "" }],
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
        {
          name: "Demo Math Tool",
          description:
            "Add built-in math tool to add/subtract/multiply/divide numbers.",
          button_text: "Connect",
          on_click: () => {
            // TODO: Register math tool
          },
        },
      ],
    },
    {
      category: "Custom Tools",
      items: [
        {
          name: "Remote MCP Servers",
          description:
            "Connect to remote MCP servers such as Firecrawl to add tools to your project.",
          href: `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/remote_mcp`,
          button_text: "Connect",
          on_click: () => {
            goto(
              `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/remote_mcp`,
            )
          },
        },
        // TODO: Add more custom tool servers
        {
          name: "Local MCP Servers",
          description: "Add or remove local MCP servers to your project.",
          button_text: "Connect",
          on_click: () => {
            goto(
              `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/local_mcp`,
            )
          },
        },
        {
          name: "RAG Servers",
          description: "Add or remove RAG servers to your project.",
          button_text: "Connect",
          // TODO: Add RAG
          on_click: () => {
            goto(
              `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/rag`,
            )
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
        <!-- Category Header -->
        <div class="pb-3 border-b border-gray-200">
          <h2 class="text-lg font-medium text-gray-900">{section.category}</h2>
        </div>

        <!-- Category Items -->
        <div class="space-y-1">
          {#each section.items as item}
            {#if item.on_click}
              <button
                on:click={item.on_click}
                class="group flex items-center justify-between py-4 px-6 rounded-lg hover:bg-gray-50 transition-all duration-200 cursor-pointer w-full text-left"
              >
                <div class="flex-1 min-w-0">
                  <h3 class="text-base font-medium text-gray-900 mb-1">
                    {item.name}
                  </h3>
                  <p class="text-sm font-light text-gray-500 leading-relaxed">
                    {item.description}
                  </p>
                </div>

                <div class="flex-shrink-0 ml-6">
                  <div
                    class="btn btn-mid group-hover:btn-primary transition-colors duration-200"
                    style="min-width: 12rem;"
                  >
                    {item.button_text}
                  </div>
                </div>
              </button>
            {/if}
          {/each}
        </div>
      </div>
    {/each}
  </div>
</AppPage>
