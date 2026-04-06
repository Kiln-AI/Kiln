<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import KilnSection from "$lib/ui/kiln_section.svelte"
  import FeatureCarousel from "$lib/ui/feature_carousel.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import {
    doc_skill_templates,
    type RequiredProvider,
    type DocSkillTemplate,
  } from "./doc_skill_templates"
  import posthog from "posthog-js"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: agentInfo.set({
    name: "Add Doc Skill",
    description: `Add a new doc skill to project ID ${project_id}. Choose from available templates or select custom.`,
  })

  let requires_api_keys_dialog: Dialog | null = null

  onMount(() => {
    load_settings()
  })

  const suggested_templates = Object.entries(doc_skill_templates).map(
    ([id, template]) => ({
      name: template.name,
      subtitle: template.preview_subtitle,
      description: template.preview_description,
      tooltip: template.preview_tooltip,
      on_click: () => {
        template_selected(template, id)
      },
    }),
  )

  let missing_provider: RequiredProvider | null = null

  function redirect_to_template(template_id: string) {
    goto(
      `/docs/doc_skills/${project_id}/create_doc_skill?template_id=${template_id}`,
    )
  }

  function template_selected(template: DocSkillTemplate, template_id: string) {
    if (settings_error) {
      alert(
        "Settings unavailable: unable to check for necessary API keys. Please refresh and try again. Error: " +
          settings_error.getMessage(),
      )
      return
    }
    if (!settings) {
      alert(
        "Settings unavailable: unable to check for necessary API keys. Please refresh and try again.",
      )
      return
    }

    missing_provider = null
    if (
      template.required_provider === "GeminiOrOpenRouter" &&
      !settings["gemini_api_key"] &&
      !settings["open_router_api_key"]
    ) {
      missing_provider = "GeminiOrOpenRouter"
      requires_api_keys_dialog?.show()
      posthog.capture("missing_api_keys_for_doc_skill", {
        template_id,
      })
      return
    }

    posthog.capture("selected_doc_skill_template", {
      template_id,
    })

    redirect_to_template(template_id)
  }

  let settings: Record<string, unknown> | undefined = undefined
  let settings_error: KilnError | null = null
  async function load_settings() {
    try {
      const { data, error } = await client.GET("/api/settings")
      if (error) {
        throw error
      }
      settings = data
    } catch (error) {
      console.error("Error loading settings", error)
      settings_error = createKilnError(error)
    }
  }

  function redirect_to_connect_provider(): boolean {
    let selected_providers = []
    if (missing_provider === "GeminiOrOpenRouter") {
      selected_providers.push("gemini_api")
      selected_providers.push("openrouter")
    }

    goto(
      `/settings/providers?required_providers=${selected_providers.join(",")}`,
    )

    progress_ui_state.set({
      title: "Creating Doc Skill",
      body: "When done adding API keys, ",
      link: $page.url.pathname,
      cta: "return to create doc skill",
      progress: null,
      step_count: null,
      current_step: null,
    })

    return true
  }
</script>

<AppPage
  title="Add a Doc Skill"
  subtitle="Convert your documents into skills that agents can browse and read"
  breadcrumbs={[
    {
      label: "Optimize",
      href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
    },
    {
      label: "Docs & Search",
      href: `/docs/${project_id}`,
    },
    {
      label: "Doc Skills",
      href: `/docs/doc_skills/${project_id}`,
    },
  ]}
>
  <div>
    <h2 class="text-lg font-medium">Suggested Configurations</h2>
    <h3 class="text-sm text-gray-500 mb-4">
      Choose a chunk size for your documents.
    </h3>
    <FeatureCarousel features={suggested_templates} />
    <div class="max-w-4xl mt-12">
      <KilnSection
        title="Custom Configuration"
        items={[
          {
            type: "settings",
            name: "Custom Doc Skill",
            badge_text: "Advanced",
            description:
              "Create a custom doc skill by specifying the document extraction method and chunking strategy. Only recommended for advanced users.",
            button_text: "Create Custom",
            on_click: () => {
              posthog.capture("clicked_custom_doc_skill")
              goto(`/docs/doc_skills/${project_id}/create_doc_skill`)
            },
          },
        ]}
      />
    </div>
  </div>
</AppPage>

<Dialog
  bind:this={requires_api_keys_dialog}
  title="Missing Required API Keys"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Add API Key",
      isPrimary: true,
      action: redirect_to_connect_provider,
    },
  ]}
>
  <div>
    <p class="mb-6">
      {#if missing_provider === "GeminiOrOpenRouter"}
        This configuration requires a Google Gemini API key or OpenRouter API
        key.
      {/if}
    </p>
  </div>
</Dialog>
