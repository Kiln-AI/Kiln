<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { ui_state } from "$lib/stores"

  let sections = [
    {
      category: "Sample Tools",
      items: [
        // TODO: Add more custom tool servers, pre-filled in.
        {
          name: "Firecrawl",
          description: "Add Firecrawl to your project to search the web.",
          button_text: "Connect",
          href: `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/firecrawl`,
        },
        {
          name: "Demo Math Tool",
          description:
            "Add built-in math tool to add/subtract/multiply/divide numbers.",
          button_text: "Connect",
          href: `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/math`,
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
        },
        // TODO: Add more custom tool servers
        {
          name: "Local MCP Servers",
          description: "Add or remove local MCP servers to your project.",
          href: `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/local_mcp`,
          button_text: "Connect",
        },
        {
          name: "RAG Servers",
          description: "Add or remove RAG servers to your project.",
          href: `/settings/manage_tools/${$ui_state?.current_project_id}/add_tools/rag`,
          button_text: "Connect",
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
            {#if item.href}
              <a
                href={item.href}
                class="group flex items-center justify-between py-4 px-6 rounded-lg hover:bg-gray-50 transition-all duration-200 cursor-pointer"
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
              </a>
            {/if}
          {/each}
        </div>
      </div>
    {/each}
  </div>
</AppPage>
