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
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import {
    rag_config_templates,
    type RequiredProvider,
    type RagConfigTemplate,
  } from "./rag_config_templates"
  import Warning from "$lib/ui/warning.svelte"
  import posthog from "posthog-js"

  $: project_id = $page.params.project_id

  let selected_template_id: string | null = null
  let selected_template: RagConfigTemplate | null = null
  let requires_api_keys_dialog: Dialog | null = null
  let requires_ollama_dialog: Dialog | null = null

  onMount(() => {
    load_settings()
  })

  const suggested_search_tools = Object.entries(rag_config_templates).map(
    ([id, template]) => ({
      name: template.name,
      subtitle: template.preview_subtitle,
      description: template.preview_description,
      tooltip: template.preview_tooltip,
      on_click: () => {
        selected_template_id = id
        selected_template = template
        suggestion_selected(template, id)
      },
    }),
  )

  let missing_provider: RequiredProvider | null = null
  $: missing_provider_string = missing_provider
    ? {
        OpenaiOrOpenRouter: "OpenAI or OpenRouter",
        GeminiOrOpenRouter: "Google Gemini or OpenRouter",
        Ollama: "Ollama",
      }[missing_provider]
    : null

  function redirect_to_template(template_id: string) {
    // Go to the create search tool page with the template id
    goto(
      `/docs/rag_configs/${project_id}/create_rag_config?template_id=${template_id}`,
    )
  }

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
    missing_provider = null
    if (
      suggestion.required_provider === "OpenaiOrOpenRouter" &&
      !settings["open_ai_api_key"] &&
      !settings["open_router_api_key"]
    ) {
      missing_provider = "OpenaiOrOpenRouter"
      requires_api_keys_dialog?.show()
      posthog.capture("missing_api_keys_for_search_tool", {
        template_id,
      })
      return
    }
    if (
      suggestion.required_provider === "GeminiOrOpenRouter" &&
      !settings["gemini_api_key"] &&
      !settings["open_router_api_key"]
    ) {
      missing_provider = "GeminiOrOpenRouter"
      requires_api_keys_dialog?.show()
      posthog.capture("missing_api_keys_for_search_tool", {
        template_id,
      })
      return
    }
    // we do not have an easy way to check if Ollama and the required models are installed
    // so we always show the dialog
    if (suggestion.required_provider === "Ollama") {
      missing_provider = "Ollama"
      requires_ollama_dialog?.show()
      posthog.capture("missing_api_keys_for_search_tool", {
        template_id,
      })
      return
    }

    posthog.capture("selected_search_tool_template", {
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
    if (missing_provider === "OpenaiOrOpenRouter") {
      selected_providers.push("openai")
      selected_providers.push("openrouter")
    } else if (missing_provider === "GeminiOrOpenRouter") {
      selected_providers.push("gemini_api")
      selected_providers.push("openrouter")
    } else if (missing_provider === "Ollama") {
      selected_providers.push("ollama")
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
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/documents-and-search-rag#building-a-search-tool"
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
      <KilnSection
        title="Custom Configuration"
        items={[
          {
            type: "settings",
            name: "Custom Search Tool",
            badge_text: "Advanced",
            description:
              "Create a custom search tool by specifying the embedding model, index type, document extraction method, and chunking strategy. Only recommended for advanced users.",
            button_text: "Create Custom",
            on_click: () => {
              posthog.capture("clicked_custom_search_tool")
              goto(`/docs/rag_configs/${project_id}/create_rag_config`)
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
      {#if missing_provider === "OpenaiOrOpenRouter"}
        This search configuration requires an OpenAI API key or OpenRouter API
        key.
      {:else if missing_provider === "GeminiOrOpenRouter"}
        This search configuration requires a Google Gemini API key or OpenRouter
        API key.
      {/if}
    </p>
    {#if settings && settings["open_router_api_key"]}
      <Warning
        warning_message="OpenRouter doesn't support embeddings yet. Please add a direct {missing_provider_string} API key for search tools."
        warning_color="warning"
        warning_icon="info"
      />
    {/if}
  </div>
</Dialog>

<Dialog
  bind:this={requires_ollama_dialog}
  title="Requires Ollama"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "I've installed the required models",
      isPrimary: true,
      action: () => {
        if (!selected_template_id) {
          return false
        }
        redirect_to_template(selected_template_id)
        return true
      },
    },
  ]}
>
  <div>
    <div class="mb-6">
      <p class="mb-2">
        This search configuration requires the following models installed in
        Ollama:
      </p>

      <ul class="list-disc list-inside mb-2">
        {#each selected_template?.required_models || [] as model}
          <li>{model}</li>
        {/each}
      </ul>
      <p class="mb-2">
        Models can be installed using the Ollama desktop app. Search for the
        model in the Ollama app, select it and send it a message. It will be
        downloaded and installed automatically.
      </p>
    </div>

    <div>
      <p>You can also install the models using the Ollama CLI:</p>
      <pre
        class="font-mono text-xs bg-base-200 p-2 rounded-md mt-1">{selected_template?.required_commands?.join(
          "\n",
        )}</pre>
    </div>
  </div>
</Dialog>
