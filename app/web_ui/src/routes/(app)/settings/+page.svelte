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
      name: "Edit Task",
      description:
        "Edit the currently selected task, including the prompt and requirements.",
      button_text: "Edit Current Task",
      href: `/settings/edit_task/${$ui_state?.current_project_id}/${$ui_state?.current_task_id}`,
    },
    {
      name: "AI Providers & Models",
      description:
        "Connect to AI providers like OpenAI, OpenRouter, or Ollama.",
      href: "/settings/providers",
      button_text: "Manage Providers & Models",
    },
    {
      name: "Manage Projects",
      description: "Add, remove or edit projects.",
      href: "/settings/manage_projects",
      button_text: "Manage Projects",
    },
    {
      name: "Edit Project",
      description: "Edit the currently selected project.",
      button_text: "Edit Current Project",
      href: "/settings/edit_project/" + $ui_state.current_project_id,
    },
    {
      name: "View Logs",
      description: "View logs of the LLM calls or the application logs.",
      button_text: "View Logs",
      on_click: view_logs,
    },
    {
      name: "App Updates",
      description: "Check if there is a new version of the app available.",
      href: "/settings/check_for_update",
      button_text: "Check for Update",
    },
    {
      name: "Replay Introduction",
      description: "Watch the introduction slide-show.",
      href: "/settings/intro",
      button_text: "Play Intro",
    },
    {
      name: "License",
      description: "View the Kiln AI desktop app License Agreement.",
      href: "https://github.com/Kiln-AI/Kiln/blob/main/app/EULA.md",
      button_text: "View EULA",
      is_external: true,
    },
  ]
</script>

<AppPage title="Settings">
  <div class="flex flex-col gap-8 max-w-[700px] mt-16">
    {#each sections as section}
      <div class="flex flex-col md:flex-row gap-4 md:items-center">
        <div class="grow">
          <h3 class="font-medium">{section.name}</h3>
          <p class="text-sm text-gray-500">{section.description}</p>
        </div>
        {#if section.href}
          <a
            href={section.href}
            class="btn"
            style="min-width: 14rem"
            target={section.is_external ? "_blank" : "_self"}
          >
            {section.button_text}
          </a>
        {:else if section.on_click}
          <button
            class="btn"
            style="min-width: 14rem"
            on:click={section.on_click}
          >
            {section.button_text}
          </button>
        {/if}
      </div>
    {/each}
  </div>
</AppPage>
