<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import SettingsSection from "$lib/ui/settings_section.svelte"
  import FeatureCarousel from "$lib/ui/feature_carousel.svelte"

  const suggested_search_tools = [
    {
      name: "Best Quality",
      subtitle: "Spare No Expense",
      description:
        "Gemini 2.5 Pro extraction, Gemini embeddings, and hybrid search.",
      on_click: () => {},
    },
    {
      name: "Cost Optimized",
      subtitle: "Balance Cost and Quality",
      description:
        "Gemini 2.5 Flash extraction, Gemini embeddings, and hybrid search.",
      on_click: () => {},
    },
    {
      name: "OpenAI Based",
      subtitle: "Need to use OpenAI?",
      description: "GPT-4o extraction, OpenAI embeddings, and hybrid search.",
      on_click: () => {},
    },
    {
      name: "Vector Only",
      subtitle: "No Full-Text Search",
      description:
        "Use only vector search for semantic similarity, not hybrid vector + full-text search.",
      on_click: () => {},
    },
  ]
</script>

<AppPage title="Create Search Tool (RAG)">
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
              "Create a custom search tool by defining the embedding model, index type, document extraction method, and chunking strategy. Only recommended for advanced users.",
            button_text: "Create Custom",
            on_click: () => {},
          },
        ]}
      />
    </div>
  </div>
</AppPage>
