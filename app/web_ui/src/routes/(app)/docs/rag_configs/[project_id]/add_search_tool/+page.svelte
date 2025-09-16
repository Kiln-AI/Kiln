<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import SettingsSection from "$lib/ui/settings_section.svelte"
  import FeatureCarousel from "$lib/ui/feature_carousel.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import {
    rag_config_templates,
    type RequiredApiKeysSets,
    type RagConfigTemplate,
  } from "./rag_config_templates"

  $: project_id = $page.params.project_id

  let requires_api_keys_dialog: Dialog | null = null

  onMount(() => {
    load_settings()
  })

  const suggested_search_tools = Object.entries(rag_config_templates).map(
    ([id, template]) => ({
      name: template.name,
      subtitle: template.preview_subtitle,
      description: template.preview_description,
      on_click: () => suggestion_selected(template, id),
      required_api_keys: template.required_api_keys,
    }),
  )

  let missing_api_keys: RequiredApiKeysSets | null = null
  function suggestion_selected(
    suggestion: RagConfigTemplate,
    template_id: string,
  ) {
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

    // Check if the user has the required API keys
    if (suggestion.required_api_keys === "OpenaiOrOpenRouter") {
      if (!settings["open_ai_api_key"] && !settings["open_router_api_key"]) {
        missing_api_keys = "OpenaiOrOpenRouter"
        requires_api_keys_dialog?.show()
        return
      }
    }
    if (suggestion.required_api_keys === "GeminiOrOpenRouter") {
      if (!settings["gemini_api_key"] && !settings["open_router_api_key"]) {
        missing_api_keys = "GeminiOrOpenRouter"
        requires_api_keys_dialog?.show()
        return
      }
    }

    // Go to the create search tool page with the template id
    goto(
      `/docs/rag_configs/${project_id}/create_rag_config?template_id=${template_id}`,
    )
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

  function add_api_key(): boolean {
    let selected_providers = []
    if (missing_api_keys === "OpenaiOrOpenRouter") {
      selected_providers.push("openai")
      selected_providers.push("openrouter")
    } else if (missing_api_keys === "GeminiOrOpenRouter") {
      selected_providers.push("gemini_api")
      selected_providers.push("openrouter")
    }
    goto(
      `/settings/providers?required_providers=${selected_providers.join(",")}`,
    )

    // Show UI to return to this page and continue
    progress_ui_state.set({
      title: "Creating Search Tool",
      body: "When done adding API keys, ",
      link: $page.url.pathname,
      cta: "return to create search tool",
      progress: null,
      step_count: null,
      current_step: null,
    })

    return true
  }
</script>

<AppPage
  title="Add a Search Tool (RAG)"
  subtitle="A tool to search for information in documents"
  breadcrumbs={[
    {
      label: "Docs & Search",
      href: `/docs/${project_id}`,
    },
    {
      label: "Search Tools",
      href: `/docs/rag_configs/${project_id}`,
    },
  ]}
>
  <div>
    <h2 class="text-lg font-medium">Suggested Configurations</h2>
    <h3 class="text-sm text-gray-500 mb-4">
      Some suggestions to get you started.
    </h3>
    <FeatureCarousel features={suggested_search_tools} />
    <div class="max-w-4xl mt-12">
      <SettingsSection
        title="Custom Configuration"
        items={[
          {
            name: "Custom Search Tool",
            badge_text: "Advanced",
            description:
              "Create a custom search tool by specifying the embedding model, index type, document extraction method, and chunking strategy. Only recommended for advanced users.",
            button_text: "Create Custom",
            href: `/docs/rag_configs/${project_id}/create_rag_config`,
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
      action: add_api_key,
    },
  ]}
>
  <p>
    {#if missing_api_keys === "OpenaiOrOpenRouter"}
      <p>
        This search configuration requires an OpenAI API key or an OpenRouter
        API key.
      </p>
    {:else if missing_api_keys === "GeminiOrOpenRouter"}
      <p>
        This search configuration requires a Google Gemini API key or an
        OpenRouter API key.
      </p>
    {/if}
  </p>
</Dialog>
