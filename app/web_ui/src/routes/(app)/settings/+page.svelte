<script lang="ts">
  import AppPage from "../app_page.svelte"
  import { ui_state } from "$lib/stores"
  import { client } from "$lib/api_client"
  import SettingsSection from "$lib/ui/settings_section.svelte"

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
      category: "Tools & MCP",
      items: [
        {
          name: "Manage Tools",
          description:
            "Connect your project to tools such as RAG systems, Kiln Tasks, and MCP servers",
          href: `/settings/manage_tools/${$ui_state?.current_project_id}`,
          button_text: "Manage Tools",
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
      category: "Help & Resources",
      items: [
        {
          name: "Application Logs",
          description:
            "View detailed logs of LLM calls and application events for debugging and monitoring.",
          button_text: "View Logs",
          on_click: view_logs,
        },
        {
          name: "Check for Update",
          description:
            "Check if there is a newer version of the Kiln app available.",
          href: "/settings/check_for_update",
          button_text: "Check for Update",
        },
        {
          name: "Docs & Getting Started",
          description:
            "Read the docs, including our getting started guide and video tutorials.",
          href: "https://docs.kiln.tech",
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
      <SettingsSection title={section.category} items={section.items} />
    {/each}
  </div>
</AppPage>
