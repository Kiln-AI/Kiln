<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import { type RagConfigTemplate } from "../add_search_tool/rag_config_templates"
  import PropertyList from "$lib/ui/property_list.svelte"

  const dispatch = createEventDispatcher<{
    customize_template: { template: RagConfigTemplate }
  }>()

  export let template: RagConfigTemplate
</script>

<div class="flex flex-col">
  <div class="mb-8">
    <PropertyList
      properties={[
        { name: "Template Name", value: template.name },
        {
          name: "Extractor Model",
          value: template.extractor.description,
          tooltip:
            "The model used to extract text from your documents (PDFs, images, videos, etc).",
        },
        {
          name: "Chunking Strategy",
          value: template.chunker.description,
          tooltip:
            "Parameters for splitting larger documents into smaller chunks for search.",
        },
        {
          name: "Embedding Model",
          value: template.embedding.description,
          tooltip:
            "The model used to convert text chunks into vectors for similarity search.",
        },
        {
          name: "Search Index",
          value: template.vector_store.description,
          tooltip:
            "How documents will be indexed and searched. Vector = semantic similarity, Full-Text = keyword search, Hybrid = both",
        },
        ...(template.notice_text
          ? [
              {
                name: "Note",
                value: template.notice_text,
                warn_icon: true,
                tooltip: template.notice_tooltip,
              },
            ]
          : []),
      ]}
    />
    <div class="flex flex-row items-center gap-2 mt-4">
      <button
        class="btn btn-sm px-6"
        on:click={() => {
          dispatch("customize_template", { template })
        }}
      >
        Customize Configuration
      </button>
      <div class="badge badge-sm badge-outline">Advanced</div>
    </div>
  </div>
</div>
