<script lang="ts">
  import AppPage from "../app_page.svelte"
  import { ui_state } from "$lib/stores"
  import { client } from "$lib/api_client"

  async function view_logs() {
    try {
      const { error } = await client.POST("/api/open_logs", {})
      if (error) {
        const errorMessage = (error as Record<string, unknown>)?.message
        if (typeof errorMessage === "string") {
          throw new Error(errorMessage)
        } else {
          throw new Error("Unknown error")
        }
      }
    } catch (e) {
      alert("Failed to open logs: " + e)
    }
  }

  let sections = [
    {
      category: "Current Workspace",
      items: [
        {
          name: "Edit Current Task",
          description:
            "Modify your current task's prompt, requirements, and configuration settings.",
          button_text: "Edit Task",
          href: `/settings/edit_task/${$ui_state?.current_project_id}/${$ui_state?.current_task_id}`,
        },
        {
          name: "Edit Current Project",
          description:
            "Update your current project's name, description, and settings.",
          button_text: "Edit Project",
          href: "/settings/edit_project/" + $ui_state.current_project_id,
        },
      ],
    },
    {
      category: "Models & Providers",
      items: [
        {
          name: "AI Providers",
          description:
            "Connect to over a dozen AI providers like Ollama, OpenRouter, Together, OpenAI and more.",
          href: "/settings/providers",
          button_text: "Manage Providers",
        },
        {
          name: "Custom Models",
          description:
            "Add or remove custom models from one of your connected AI providers.",
          href: "/settings/providers/add_models",
          button_text: "Custom Models",
        },
      ],
    },
    {
      category: "Projects",
      items: [
        {
          name: "Manage Projects",
          description:
            "Create new projects, organize existing ones, or remove projects you no longer need.",
          href: "/settings/manage_projects",
          button_text: "Manage Projects",
        },
      ],
    },
    {
      category: "Tools & Support",
      items: [
        {
          name: "Application Logs",
          description:
            "View detailed logs of LLM calls and application events for debugging and monitoring.",
          button_text: "View Logs",
          on_click: view_logs,
        },
        {
          name: "App Updates",
          description:
            "Check for the latest version of Kiln AI and install updates when available.",
          href: "/settings/check_for_update",
          button_text: "Check for Update",
        },
        {
          name: "Docs & Getting Started",
          description:
            "Read the docs, including our getting started guide and video tutorials.",
          href: "https://docs.getkiln.ai",
          button_text: "Docs & Guides",
          is_external: true,
        },
        {
          name: "License Agreement",
          description:
            "View the End User License Agreement (EULA) for the Kiln AI desktop application.",
          href: "https://github.com/Kiln-AI/Kiln/blob/main/app/EULA.md",
          button_text: "View EULA",
          is_external: true,
        },
      ],
    },
  ]
</script>

<AppPage title="Settings">
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
                target={item.is_external ? "_blank" : null}
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
                    {#if item.is_external}
                      <svg
                        class="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        ></path>
                      </svg>
                    {/if}
                  </div>
                </div>
              </a>
            {:else if item.on_click}
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
