<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createEventDispatcher, onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import TagSelector from "./tag_selector.svelte"
  import type {
    ExtractorConfig,
    ChunkerConfig,
    EmbeddingConfig,
    VectorStoreConfig,
  } from "$lib/types"
  import { load_available_embedding_models } from "$lib/stores"
  import Collapse from "$lib/ui/collapse.svelte"
  import {
    build_rag_config_sub_configs,
    type RagConfigTemplate,
  } from "../add_search_tool/rag_config_templates"
  import { tool_name_validator } from "$lib/utils/input_validators"
  import posthog from "posthog-js"
  import { uncache_available_tools } from "$lib/stores"
  import CreateChunkerDialog from "./create_chunker_dialog.svelte"
  import CreateEmbeddingDialog from "./create_embedding_dialog.svelte"
  import CreateVectorStoreDialog from "./create_vector_store_dialog.svelte"
  import CreateExtractorDialog from "./create_extractor_dialog.svelte"
  import {
    build_chunker_options,
    build_embedding_options,
    build_extractor_options,
    build_vector_store_options,
  } from "./options_groups"
  import TemplatePropertyOverview from "./template_property_overview.svelte"
  import type { RagConfigWithSubConfigs } from "$lib/types"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import {
    fixedWindowChunkerProperties,
    semanticChunkerProperties,
  } from "$lib/utils/properties_cast"

  const dispatch = createEventDispatcher<{
    success: { rag_config_id: string }
  }>()

  $: project_id = $page.params.project_id
  export let template: RagConfigTemplate | null = null
  export let initial_rag_config: RagConfigWithSubConfigs | null = null
  let customize_template_mode = false

  let error: KilnError | null = null
  let tool_name: string
  let tool_description: string
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

  let loading: boolean = false
  let loading_extractor_configs = false
  let loading_chunker_configs = false
  let loading_embedding_configs = false
  let loading_vector_store_configs = false
  $: loading_subconfig_options =
    loading_extractor_configs ||
    loading_chunker_configs ||
    loading_embedding_configs ||
    loading_vector_store_configs

  // track which modal is currently open to disable the keyboard submit for other forms
  // otherwise keyboard shortcut will submit all the existing forms
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

  // build fancy select options from configs
  $: extractor_options = build_extractor_options(extractor_configs)
  $: chunker_options = build_chunker_options(chunker_configs)
  $: embedding_options = build_embedding_options(embedding_configs)
  $: vector_store_options = build_vector_store_options(vector_store_configs)

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

  function fill_out_form_from_rag_config(rag_config: RagConfigWithSubConfigs) {
    name = rag_config.name
    description = rag_config.description || ""
    tool_name = rag_config.tool_name
    tool_description = rag_config.tool_description
    selected_extractor_config_id = rag_config.extractor_config.id || null
    selected_chunker_config_id = rag_config.chunker_config.id || null
    selected_embedding_config_id = rag_config.embedding_config.id || null
    selected_vector_store_config_id = rag_config.vector_store_config.id || null
    selected_tags = rag_config.tags || []
  }

  onMount(async () => {
    if (initial_rag_config && template) {
      console.warn(
        "Cannot have both initial rag config and template. Discarding initial_rag_config.",
      )
      initial_rag_config = null
    }

    await Promise.all([
      load_available_embedding_models(),
      loadExtractorConfigs(),
      loadChunkerConfigs(),
      loadEmbeddingConfigs(),
      loadVectorStoreConfigs(),
    ])

    if (initial_rag_config) {
      fill_out_form_from_rag_config(initial_rag_config)
    }
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
        throw fetch_error
      }

      extractor_configs = data || []
    } catch (e) {
      error = createKilnError(e)
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
        throw fetch_error
      }

      chunker_configs = data || []
    } catch (e) {
      error = createKilnError(e)
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
        throw fetch_error
      }

      embedding_configs = data || []
    } catch (e) {
      error = createKilnError(e)
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
        throw fetch_error
      }

      vector_store_configs = data || []
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading_vector_store_configs = false
    }
  }

  /**
   * Save the rag config from the full form
   */
  async function create_rag_config() {
    try {
      loading = true
      error = null

      if (!tool_name || !tool_name.trim()) {
        throw new Error("Please provide a search tool name.")
      }

      if (!tool_description || !tool_description.trim()) {
        throw new Error("Please provide a search tool description.")
      }

      // Validate that all required configs are selected
      if (
        !selected_extractor_config_id ||
        selected_extractor_config_id === "create_new"
      ) {
        throw new Error("Please select an extractor configuration.")
      }

      if (
        !selected_chunker_config_id ||
        selected_chunker_config_id === "create_new"
      ) {
        throw new Error("Please select a chunker configuration.")
      }

      if (
        !selected_embedding_config_id ||
        selected_embedding_config_id === "create_new"
      ) {
        throw new Error("Please select an embedding configuration.")
      }

      if (
        !selected_vector_store_config_id ||
        selected_vector_store_config_id === "create_new"
      ) {
        throw new Error("Please select a search index configuration.")
      }

      const { data: create_rag_config_res, error: create_error } =
        await client.POST(
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
        throw create_error
      }

      if (!create_rag_config_res?.id) {
        throw new Error("Failed to create RAG config: missing id")
      }

      let extractor_model: string | undefined = undefined
      let chunker_type: "fixed_window" | "semantic" | undefined = undefined
      let chunker_size: unknown = undefined
      let chunker_overlap: unknown = undefined
      let embedding_model: string | undefined = undefined
      let vector_store_type: string | undefined = undefined
      let breakpoint_percentile_threshold: unknown = undefined
      let buffer_size: unknown = undefined
      try {
        extractor_model = extractor_configs.find(
          (config) => config.id === selected_extractor_config_id,
        )?.model_name
        embedding_model = embedding_configs.find(
          (config) => config.id === selected_embedding_config_id,
        )?.model_name
        vector_store_type = vector_store_configs.find(
          (config) => config.id === selected_vector_store_config_id,
        )?.store_type

        const chunker_config = chunker_configs.find(
          (config) => config.id === selected_chunker_config_id,
        )
        chunker_type = chunker_config?.chunker_type

        if (chunker_type === "fixed_window" && chunker_config) {
          const fixed_window_properties =
            fixedWindowChunkerProperties(chunker_config)
          chunker_size = fixed_window_properties.chunk_size
          chunker_overlap = fixed_window_properties.chunk_overlap
        } else if (chunker_type === "semantic" && chunker_config) {
          const semantic_properties = semanticChunkerProperties(chunker_config)
          breakpoint_percentile_threshold =
            semantic_properties.breakpoint_percentile_threshold
          buffer_size = semantic_properties.buffer_size
        }
      } catch (e) {
        console.error(e)
      }
      posthog.capture("create_custom_rag_config", {
        tag_filter: selected_tags.length > 0,
        extractor_model: extractor_model,
        chunker_type: chunker_type,
        chunker_size: chunker_size,
        chunker_overlap: chunker_overlap,
        chunker_breakpoint_percentile_threshold:
          breakpoint_percentile_threshold,
        chunker_buffer_size: buffer_size,
        embedding_model: embedding_model,
        vector_store_type: vector_store_type,
        // tool_name and tool_description have no defaults, requiring user input
        // but we keep these for backwards compatibility of the event (we had a default before)
        custom_name: true,
        custom_description: true,
      })

      uncache_available_tools(project_id)

      dispatch("success", { rag_config_id: create_rag_config_res.id })
    } catch (err) {
      error = createKilnError(err)
      return
    } finally {
      loading = false
    }
  }

  /**
   * Fill out the full form from the template
   */
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

  /**
   * Save all the subconfigs and then create the rag config from the template
   */
  async function save_template() {
    if (!template) {
      return
    }

    try {
      loading = true

      if (!tool_name || !tool_name.trim()) {
        throw new Error("Please provide a search tool name.")
      }

      if (!tool_description || !tool_description.trim()) {
        throw new Error("Please provide a search tool description.")
      }

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
      const { data: create_rag_config_res, error: create_error } =
        await client.POST(
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
        throw create_error
      }

      if (!create_rag_config_res?.id) {
        throw new Error("Failed to create RAG config: missing id")
      }

      posthog.capture("create_rag_config_from_template", {
        template_name: template.name,
        tag_filter: selected_tags.length > 0,
        // tool_name and tool_description have no defaults, requiring user input
        // but we keep these for backwards compatibility of the event (we had a default before)
        custom_name: true,
        custom_description: true,
      })

      uncache_available_tools(project_id)

      dispatch("success", { rag_config_id: create_rag_config_res.id })
    } catch (err) {
      error = createKilnError(err)
      return
    } finally {
      loading = false
    }
  }
</script>

{#if loading || loading_subconfig_options}
  <div class="w-full min-h-[50vh] flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else}
  <FormContainer
    submit_visible={true}
    submit_label="Create Search Tool"
    on:submit={async () => {
      if (template && !customize_template_mode) {
        await save_template()
      } else {
        await create_rag_config()
      }
    }}
    {error}
    gap={4}
    bind:submitting={loading}
    keyboard_submit={!modal_opened}
  >
    <!-- Search Tool Properties -->
    <div class="text-xl font-bold">Part 1: Tool Properties</div>
    <FormElement
      label="Search Tool Name"
      description="A unique short tool name such as 'knowledge_base_search'. Be descriptive about what data this tool can search."
      info_description="Must be in snake_case format. It should be descriptive of what the tool does as the model will see it. When adding multiple tools to a task each tool needs a unique name, so being unique and descriptive is important."
      inputType="input"
      id="tool_name"
      bind:value={tool_name}
      validator={tool_name_validator}
      placeholder="e.g. knowledge_base_search, customer_support_search"
    />
    <FormElement
      label="Search Tool Description"
      description="A description for the model to understand what this tool can do, and when to use it. Include a description of what data this tool can search."
      info_description="It should be descriptive of what the tool does as the model will see it. Example of a high quality description: 'Search the customer facing help docs for information about the product.'"
      inputType="textarea"
      id="tool_description"
      max_length={128}
      bind:value={tool_description}
      placeholder="e.g. Search the ACME Inc. knowledge base for information about the product."
    />

    <!-- Tag Selection -->
    <div class="flex flex-col gap-2">
      <TagSelector
        {project_id}
        bind:selected_tags
        on:change={(e) => (selected_tags = e.detail.selected_tags)}
      />
    </div>

    <div>
      <div class="text-xl font-bold mt-4">Part 2: Search Configuration</div>
      <div class="text-xs text-gray-500 font-medium">
        This configuration controls how the search tool will extract, index, and
        search your documents.
        {#if template && !customize_template_mode}
          <InfoTooltip
            no_pad={true}
            tooltip_text="You selected a pre-configured search tool with these parameters."
          />
        {/if}
      </div>
    </div>

    {#if template && !customize_template_mode}
      <TemplatePropertyOverview
        {template}
        on:customize_template={customize_template}
      />
    {:else}
      <div class="flex flex-col gap-6">
        <!-- Extractor Selection -->
        <div class="flex flex-col gap-2">
          <FormElement
            id="extractor_select"
            label="Extractor"
            description="Extractors convert your documents into text."
            info_description="Documents like PDFs, images and videos need to be converted into text so they can be searched and read by models."
            fancy_select_options={extractor_options}
            bind:value={selected_extractor_config_id}
            inputType="fancy_select"
          />
        </div>

        <!-- Chunker Selection -->
        <div class="flex flex-col gap-2">
          <FormElement
            id="chunker_select"
            label="Chunker"
            description="Split document text into smaller chunks for search."
            info_description="Splitting long documents into smaller chunks allows search to find relevant information."
            fancy_select_options={chunker_options}
            bind:value={selected_chunker_config_id}
            inputType="fancy_select"
          />
        </div>

        <!-- Embedding Selection -->
        <div class="flex flex-col gap-2">
          <FormElement
            id="embedding_select"
            label="Embedding Model"
            description="Embedding models convert document chunks into vectors for similarity search."
            info_description="Embedding models are a type of AI model which create searchable vectors from your chunks."
            fancy_select_options={embedding_options}
            bind:value={selected_embedding_config_id}
            inputType="fancy_select"
          />
        </div>

        <!-- Vector Store Selection -->
        <div class="flex flex-col gap-2">
          <FormElement
            id="vector_store_select"
            label="Search Index"
            description="Choose how documents will be indexed and searched."
            info_description="Full text search is fastest for keyword searches, vector search is best for semantic meaning, and hybrid combines both approaches."
            fancy_select_options={vector_store_options}
            bind:value={selected_vector_store_config_id}
            inputType="fancy_select"
          />
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
{/if}

<CreateExtractorDialog
  bind:dialog={show_create_extractor_dialog}
  keyboard_submit={modal_opened === "extractor"}
  on:success={async (e) => {
    await loadExtractorConfigs()
    selected_extractor_config_id = e.detail.extractor_config_id
  }}
  on:close={() => {
    handle_modal_close()
    if (selected_extractor_config_id === "create_new") {
      selected_extractor_config_id = null
    }
    show_create_extractor_dialog?.close()
  }}
/>

<CreateChunkerDialog
  bind:dialog={show_create_chunker_dialog}
  keyboard_submit={modal_opened === "chunker"}
  on:success={async (e) => {
    await loadChunkerConfigs()
    selected_chunker_config_id = e.detail.chunker_config_id
  }}
  on:close={() => {
    handle_modal_close()
    if (selected_chunker_config_id === "create_new") {
      selected_chunker_config_id = null
    }
    show_create_chunker_dialog?.close()
  }}
/>

<CreateEmbeddingDialog
  bind:dialog={show_create_embedding_dialog}
  keyboard_submit={modal_opened === "embedding"}
  on:success={async (e) => {
    await loadEmbeddingConfigs()
    selected_embedding_config_id = e.detail.embedding_config_id
  }}
  on:close={() => {
    handle_modal_close()
    if (selected_embedding_config_id === "create_new") {
      selected_embedding_config_id = null
    }
    show_create_embedding_dialog?.close()
  }}
/>

<CreateVectorStoreDialog
  bind:dialog={show_create_vector_store_dialog}
  keyboard_submit={modal_opened === "vector_store"}
  on:success={async (e) => {
    await loadVectorStoreConfigs()
    selected_vector_store_config_id = e.detail.vector_store_config_id
  }}
  on:close={() => {
    handle_modal_close()
    if (selected_vector_store_config_id === "create_new") {
      selected_vector_store_config_id = null
    }
    show_create_vector_store_dialog?.close()
  }}
/>
