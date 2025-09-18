<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { goto } from "$app/navigation"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateExtractorForm from "../../../extractors/[project_id]/create_extractor/create_extractor_form.svelte"
  import CreateChunkerForm from "./create_chunker_form.svelte"
  import CreateEmbeddingForm from "./create_embedding_form.svelte"
  import CreateVectorStoreForm from "./create_vector_store_form.svelte"
  import TagSelector from "./tag_selector.svelte"
  import type {
    ExtractorConfig,
    ChunkerConfig,
    EmbeddingConfig,
    VectorStoreConfig,
  } from "$lib/types"
  import {
    embedding_model_name,
    get_model_friendly_name,
    load_available_embedding_models,
    provider_name_from_id,
  } from "$lib/stores"
  import Collapse from "$lib/ui/collapse.svelte"
  import { extractor_output_format } from "$lib/utils/formatters"
  import {
    rag_config_templates,
    build_rag_config_sub_configs,
  } from "../add_search_tool/rag_config_templates"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { tool_name_validator } from "$lib/utils/input_validators"

  $: project_id = $page.params.project_id
  const template_id = $page.url.searchParams.get("template_id")
  const template = template_id ? rag_config_templates[template_id] : null
  let customize_template_mode = false

  let loading: boolean = false
  let error: KilnError | null = null
  let tool_name: string = "search_docs"
  let tool_description: string = "Search documents for knowledge."
  let name: string | null = null
  let description: string = ""
  let selected_tags: string[] = []

  let show_create_extractor_dialog: Dialog | null = null
  let show_create_chunker_dialog: Dialog | null = null
  let show_create_embedding_dialog: Dialog | null = null
  let show_create_vector_store_dialog: Dialog | null = null

  // Selected configs
  let selected_extractor_config_id: string | null = null
  let selected_chunker_config_id: string | null = null
  let selected_embedding_config_id: string | null = null
  let selected_vector_store_config_id: string | null = null

  // Data for dropdowns
  let extractor_configs: ExtractorConfig[] = []
  let chunker_configs: ChunkerConfig[] = []
  let embedding_configs: EmbeddingConfig[] = []
  let vector_store_configs: VectorStoreConfig[] = []

  // Loading states for data fetching
  let loading_extractor_configs = false
  let loading_chunker_configs = false
  let loading_embedding_configs = false
  let loading_vector_store_configs = false

  // track which modal is currently open to disable the other forms
  let modal_opened:
    | "extractor"
    | "chunker"
    | "embedding"
    | "vector_store"
    | null = null

  function handle_modal_open(
    modal_type: "extractor" | "chunker" | "embedding" | "vector_store",
  ) {
    modal_opened = modal_type
  }

  function handle_modal_close() {
    modal_opened = null
  }

  function extractor_label(extractor: ExtractorConfig) {
    return `${get_model_friendly_name(extractor.model_name)} (${provider_name_from_id(extractor.model_provider_name)}) - ${extractor_output_format(extractor.output_format)}`
  }

  // Convert configs to option groups for fancy select
  $: extractor_options = [
    {
      options: [
        {
          label: "New Extractor Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },

    ...(extractor_configs.length > 0
      ? [
          {
            label: "Extractors",
            options: extractor_configs
              .filter((config) => !config.is_archived)
              .map((config) => ({
                label: extractor_label(config),
                value: config.id,
                description:
                  config.name +
                  (config.description ? " - " + config.description : ""),
              })),
          },
        ]
      : []),
  ] as OptionGroup[]

  $: chunker_options = [
    {
      options: [
        {
          label: "New Chunker Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(chunker_configs.length > 0
      ? [
          {
            label: "Chunkers",
            options: chunker_configs.map((config) => ({
              // Build label only from defined properties
              label: [
                config.properties?.chunk_size !== null &&
                config.properties.chunk_size !== undefined
                  ? `Size: ${config.properties.chunk_size} words`
                  : null,
                config.properties?.chunk_overlap !== null &&
                config.properties.chunk_overlap !== undefined
                  ? `Overlap: ${config.properties.chunk_overlap} words`
                  : null,
              ]
                .filter(Boolean)
                .join(" - "),
              value: config.id,
              description:
                config.name +
                (config.description ? ` - ${config.description}` : ""),
            })),
          },
        ]
      : []),
  ] as OptionGroup[]

  $: embedding_options = [
    {
      options: [
        {
          label: "New Embedding Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(embedding_configs.length > 0
      ? [
          {
            label: "Embedding Models",
            options: embedding_configs.map((config) => ({
              label:
                `${embedding_model_name(config.model_name, config.model_provider_name)} (${provider_name_from_id(config.model_provider_name)})` +
                (config.properties?.dimensions
                  ? `- ${config.properties?.dimensions} dimensions`
                  : ""),
              value: config.id,
              description:
                config.name +
                (config.description ? " - " + config.description : ""),
            })),
          },
        ]
      : []),
  ] as OptionGroup[]

  $: vector_store_options = [
    {
      options: [
        {
          label: "New Search Index Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(vector_store_configs.length > 0
      ? [
          {
            label: "Search Index Configurations",
            options: vector_store_configs.map((config) => ({
              label:
                config.store_type === "lancedb_fts"
                  ? "Full Text Search"
                  : config.store_type === "lancedb_vector"
                    ? "Vector Search"
                    : "Hybrid Search",
              value: config.id,
              description:
                config.name +
                ` (${config.properties.similarity_top_k || 10} results)`,
            })),
          },
        ]
      : []),
  ] as OptionGroup[]

  // show the create extractor dialog when the user clicks the create new extractor button
  $: if (selected_extractor_config_id === "create_new") {
    show_create_extractor_dialog?.show()
    handle_modal_open("extractor")
  } else {
    show_create_extractor_dialog?.close()
  }

  // show the create chunker dialog when the user clicks the create new chunker button
  $: if (selected_chunker_config_id === "create_new") {
    show_create_chunker_dialog?.show()
    handle_modal_open("chunker")
  } else {
    show_create_chunker_dialog?.close()
  }

  // show the create embedding dialog when the user clicks the create new embedding button
  $: if (selected_embedding_config_id === "create_new") {
    show_create_embedding_dialog?.show()
    handle_modal_open("embedding")
  } else {
    show_create_embedding_dialog?.close()
  }

  // show the create vector store dialog when the user clicks the create new vector store button
  $: if (selected_vector_store_config_id === "create_new") {
    show_create_vector_store_dialog?.show()
    handle_modal_open("vector_store")
  } else {
    show_create_vector_store_dialog?.close()
  }

  // Load data on mount
  onMount(async () => {
    await Promise.all([
      load_available_embedding_models(),
      loadExtractorConfigs(),
      loadChunkerConfigs(),
      loadEmbeddingConfigs(),
      loadVectorStoreConfigs(),
    ])
  })

  async function loadExtractorConfigs() {
    try {
      loading_extractor_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/extractor_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        error = createKilnError(fetch_error)
        return
      }

      extractor_configs = data || []
    } finally {
      loading_extractor_configs = false
    }
  }

  async function loadChunkerConfigs() {
    try {
      loading_chunker_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/chunker_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        error = createKilnError(fetch_error)
        return
      }

      chunker_configs = data || []
    } finally {
      loading_chunker_configs = false
    }
  }

  async function loadEmbeddingConfigs() {
    try {
      loading_embedding_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/embedding_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        error = createKilnError(fetch_error)
        return
      }

      embedding_configs = data || []
    } finally {
      loading_embedding_configs = false
    }
  }

  async function loadVectorStoreConfigs() {
    try {
      loading_vector_store_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/vector_store_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        error = createKilnError(fetch_error)
        return
      }

      vector_store_configs = data || []
    } finally {
      loading_vector_store_configs = false
    }
  }

  async function create_rag_config() {
    // Special case for saving the template
    if (template && !customize_template_mode) {
      await save_template()
      return
    }

    try {
      loading = true
      error = null

      // Validate that all required configs are selected
      if (
        !selected_extractor_config_id ||
        selected_extractor_config_id === "create_new"
      ) {
        error = createKilnError({
          message: "Please select an extractor configuration.",
          status: 400,
        })
        return
      }

      if (
        !selected_chunker_config_id ||
        selected_chunker_config_id === "create_new"
      ) {
        error = createKilnError({
          message: "Please select a chunker configuration.",
          status: 400,
        })
        return
      }

      if (
        !selected_embedding_config_id ||
        selected_embedding_config_id === "create_new"
      ) {
        error = createKilnError({
          message: "Please select an embedding configuration.",
          status: 400,
        })
        return
      }

      if (
        !selected_vector_store_config_id ||
        selected_vector_store_config_id === "create_new"
      ) {
        error = createKilnError({
          message: "Please select a vector store configuration.",
          status: 400,
        })
        return
      }

      const { error: create_error } = await client.POST(
        "/api/projects/{project_id}/rag_configs/create_rag_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name || null,
            description: description || null,
            tool_name: tool_name,
            tool_description: tool_description,
            extractor_config_id: selected_extractor_config_id,
            chunker_config_id: selected_chunker_config_id,
            embedding_config_id: selected_embedding_config_id,
            vector_store_config_id: selected_vector_store_config_id,
            tags: selected_tags.length > 0 ? selected_tags : null,
          },
        },
      )

      if (create_error) {
        error = createKilnError(create_error)
        return
      }

      goto(`/docs/rag_configs/${project_id}`)
    } finally {
      loading = false
    }
  }

  async function customize_template() {
    if (!template) {
      return
    }
    try {
      loading = true
      // Fetch or build the sub configs
      const {
        extractor_config_id,
        chunker_config_id,
        embedding_config_id,
        vector_store_config_id,
      } = await build_rag_config_sub_configs(
        template,
        project_id,
        extractor_configs,
        chunker_configs,
        embedding_configs,
        vector_store_configs,
      )
      // Reload the configs, new ones may have been created in above step
      await Promise.all([
        loadExtractorConfigs(),
        loadChunkerConfigs(),
        loadEmbeddingConfigs(),
        loadVectorStoreConfigs(),
      ])
      // Update the UI with the new configs
      selected_extractor_config_id = extractor_config_id
      selected_chunker_config_id = chunker_config_id
      selected_embedding_config_id = embedding_config_id
      selected_vector_store_config_id = vector_store_config_id
      // Don't render the template anymore, let them customize it
      customize_template_mode = true
    } catch (err) {
      error = createKilnError("Error customizing template: " + err)
      return
    } finally {
      loading = false
    }
  }

  async function save_template() {
    if (!template) {
      return
    }
    try {
      loading = true

      // Fetch or build the sub configs
      const {
        extractor_config_id,
        chunker_config_id,
        embedding_config_id,
        vector_store_config_id,
      } = await build_rag_config_sub_configs(
        template,
        project_id,
        extractor_configs,
        chunker_configs,
        embedding_configs,
        vector_store_configs,
      )

      // Save the rag config
      const { error: create_error } = await client.POST(
        "/api/projects/{project_id}/rag_configs/create_rag_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: template.rag_config_name,
            tool_name: tool_name,
            tool_description: tool_description,
            extractor_config_id,
            chunker_config_id,
            embedding_config_id,
            vector_store_config_id,
            tags: selected_tags.length > 0 ? selected_tags : null,
          },
        },
      )

      if (create_error) {
        error = createKilnError(create_error)
        return
      }

      goto(`/docs/rag_configs/${project_id}`)
    } finally {
      loading = false
    }
  }
</script>

<AppPage
  title="Create Search Tool (RAG)"
  subtitle="Define parameters for how this tool will search and retrieve your documents"
  breadcrumbs={[
    {
      label: "Docs & Search",
      href: `/docs/${project_id}`,
    },
    {
      label: "Search Tools",
      href: `/docs/rag_configs/${project_id}`,
    },
    {
      label: "Add Search Tool",
      href: `/docs/rag_configs/${project_id}/add_search_tool`,
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else}
    <div class="max-w-[900px]">
      <FormContainer
        submit_visible={true}
        submit_label="Create Search Tool"
        on:submit={create_rag_config}
        {error}
        gap={4}
        bind:submitting={loading}
        keyboard_submit={!modal_opened}
      >
        <!-- Search Tool Properties -->
        <FormElement
          label="Search Tool Name"
          description="A unique short tool name such as 'knowledge_base_search'. Be descriptive about what data this tool can search."
          info_description="Must be in snake_case format. It should be descriptive of what the tool does as the model will see it. When adding multiple tools to a task each tool needs a unique name, so being unique and descriptive is important."
          inputType="input"
          id="tool_name"
          bind:value={tool_name}
          validator={tool_name_validator}
        />
        <FormElement
          label="Search Tool Description"
          description="A description for the model to understand what this tool can do, and when to use it. Include a description of what data this tool can search."
          info_description="It should be descriptive of what the tool does as the model will see it. Example of a high quality description: 'Search the customer facing help docs for information about the product.'"
          inputType="textarea"
          id="tool_description"
          max_length={128}
          bind:value={tool_description}
        />

        <!-- Tag Selection -->
        <div class="flex flex-col gap-2">
          <TagSelector
            {project_id}
            bind:selected_tags
            on:change={(e) => (selected_tags = e.detail.selected_tags)}
          />
        </div>
        {#if template && !customize_template_mode}
          <div class="flex flex-col mt-4">
            <FormElement
              id="search_tool_configuration_header"
              label="Search Configuration"
              description="These parameters control how the search tool will extract, index, and search your documents."
              info_description="You selected a pre-configured search tool with these parameters."
              inputType="header_only"
              value={null}
            />
            <div class="mt-2 mb-8">
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
                    name: "Chunker",
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
              <button
                class="btn mt-4 btn-sm px-6"
                on:click={() => {
                  customize_template()
                }}
              >
                Customize Configuration
                <span class="badge badge-sm badge-outline">Advanced</span>
              </button>
            </div>
          </div>
        {:else}
          <div class="flex flex-col gap-6">
            <!-- Extractor Selection -->
            <div class="flex flex-col gap-2">
              {#if loading_extractor_configs}
                <div class="flex items-center gap-2">
                  <div class="loading loading-spinner loading-sm"></div>
                  <span class="text-sm">Loading extractors...</span>
                </div>
              {:else}
                <FormElement
                  id="extractor_select"
                  label="Extractor"
                  description="Extractors convert your documents into text."
                  info_description="Documents like PDFs, images and videos need to be converted into text so they can be searched and read by models."
                  fancy_select_options={extractor_options}
                  bind:value={selected_extractor_config_id}
                  inputType="fancy_select"
                />
              {/if}
            </div>

            <!-- Chunker Selection -->
            <div class="flex flex-col gap-2">
              {#if loading_chunker_configs}
                <div class="flex items-center gap-2">
                  <div class="loading loading-spinner loading-sm"></div>
                  <span class="text-sm">Loading chunkers...</span>
                </div>
              {:else}
                <FormElement
                  id="chunker_select"
                  label="Chunker"
                  description="Split document text into smaller chunks for search."
                  info_description="Splitting long documents into smaller chunks allows search to find relevant information."
                  fancy_select_options={chunker_options}
                  bind:value={selected_chunker_config_id}
                  inputType="fancy_select"
                />
              {/if}
            </div>

            <!-- Embedding Selection -->
            <div class="flex flex-col gap-2">
              {#if loading_embedding_configs}
                <div class="flex items-center gap-2">
                  <div class="loading loading-spinner loading-sm"></div>
                  <span class="text-sm">Loading embedding models...</span>
                </div>
              {:else}
                <FormElement
                  id="embedding_select"
                  label="Embedding Model"
                  description="Embedding models convert document chunks into vectors for similarity search."
                  info_description="Embedding models are a type of AI model which create searchable vectors from your chunks."
                  fancy_select_options={embedding_options}
                  bind:value={selected_embedding_config_id}
                  inputType="fancy_select"
                />
              {/if}
            </div>

            <!-- Vector Store Selection -->
            <div class="flex flex-col gap-2">
              {#if loading_vector_store_configs}
                <div class="flex items-center gap-2">
                  <div class="loading loading-spinner loading-sm"></div>
                  <span class="text-sm">Loading vector stores...</span>
                </div>
              {:else}
                <FormElement
                  id="vector_store_select"
                  label="Search Index"
                  description="Choose how documents will be indexed and searched."
                  info_description="Full text search is fastest for keyword searches, vector search is best for semantic meaning, and hybrid combines both approaches."
                  fancy_select_options={vector_store_options}
                  bind:value={selected_vector_store_config_id}
                  inputType="fancy_select"
                />
              {/if}
            </div>
          </div>

          <!-- Advanced -->
          <Collapse title="Advanced Options">
            <FormElement
              label="Reference Name"
              description="A search tool name for your reference, not seen by the model. Leave blank and we'll generate one for you."
              optional={true}
              inputType="input"
              id="rag_config_name"
              bind:value={name}
            />
            <FormElement
              label="Reference Description"
              description="A description of the search tool for your reference, not seen by the model."
              optional={true}
              inputType="textarea"
              id="rag_config_description"
              bind:value={description}
            />
          </Collapse>
        {/if}
      </FormContainer>
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={show_create_extractor_dialog}
  title="Extractor Configuration"
  subtitle="Extractors convert your documents into text."
  width="wide"
  on:close={() => {
    handle_modal_close()
    if (selected_extractor_config_id === "create_new") {
      selected_extractor_config_id = null
    }
  }}
>
  <CreateExtractorForm
    keyboard_submit={modal_opened === "extractor"}
    on:success={async (e) => {
      await loadExtractorConfigs()
      selected_extractor_config_id = e.detail.extractor_config_id
    }}
  />
</Dialog>

<Dialog
  bind:this={show_create_chunker_dialog}
  title="Chunker Configuration"
  subtitle="Split document text into smaller chunks for search."
  width="wide"
  on:close={() => {
    handle_modal_close()
    if (selected_chunker_config_id === "create_new") {
      selected_chunker_config_id = null
    }
  }}
>
  <CreateChunkerForm
    keyboard_submit={modal_opened === "chunker"}
    on:success={async (e) => {
      await loadChunkerConfigs()
      selected_chunker_config_id = e.detail.chunker_config_id
    }}
  />
</Dialog>

<Dialog
  bind:this={show_create_embedding_dialog}
  title="Embedding Configuration"
  subtitle="Convert text chunks into vectors for similarity search."
  width="normal"
  on:close={() => {
    handle_modal_close()
    if (selected_embedding_config_id === "create_new") {
      selected_embedding_config_id = null
    }
  }}
>
  <CreateEmbeddingForm
    keyboard_submit={modal_opened === "embedding"}
    on:success={async (e) => {
      await loadEmbeddingConfigs()
      selected_embedding_config_id = e.detail.embedding_config_id
    }}
  />
</Dialog>

<Dialog
  bind:this={show_create_vector_store_dialog}
  title="Search Index Configuration"
  subtitle="Choose how documents will be indexed and searched."
  width="wide"
  on:close={() => {
    handle_modal_close()
    if (selected_vector_store_config_id === "create_new") {
      selected_vector_store_config_id = null
    }
  }}
>
  <CreateVectorStoreForm
    keyboard_submit={modal_opened === "vector_store"}
    on:success={async (e) => {
      await loadVectorStoreConfigs()
      selected_vector_store_config_id = e.detail.vector_store_config_id
    }}
  />
</Dialog>
