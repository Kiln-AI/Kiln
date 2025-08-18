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
  import type {
    ExtractorConfig,
    ChunkerConfig,
    EmbeddingConfig,
  } from "$lib/types"
  import {
    embedding_model_name,
    get_model_friendly_name,
    load_available_embedding_models,
    provider_name_from_id,
  } from "$lib/stores"
  import Collapse from "$lib/ui/collapse.svelte"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string | null = null
  let description: string = ""

  let show_create_extractor_dialog: Dialog | null = null
  let show_create_chunker_dialog: Dialog | null = null
  let show_create_embedding_dialog: Dialog | null = null

  // Selected configs
  let selected_extractor_config_id: string | null = null
  let selected_chunker_config_id: string | null = null
  let selected_embedding_config_id: string | null = null

  // Data for dropdowns
  let extractor_configs: ExtractorConfig[] = []
  let chunker_configs: ChunkerConfig[] = []
  let embedding_configs: EmbeddingConfig[] = []

  // Loading states for data fetching
  let loading_extractor_configs = false
  let loading_chunker_configs = false
  let loading_embedding_configs = false

  // track which modal is currently open to disable the other forms
  let modal_opened: "extractor" | "chunker" | "embedding" | null = null

  function handle_modal_open(
    modal_type: "extractor" | "chunker" | "embedding",
  ) {
    modal_opened = modal_type
  }

  function handle_modal_close() {
    modal_opened = null
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
                label: `${get_model_friendly_name(config.model_name)} (${provider_name_from_id(config.model_provider_name)}) - ${config.output_format}`,
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
              label: `Size: ${config.properties?.chunk_size} tokens - Overlap: ${config.properties?.chunk_overlap} tokens`,
              value: config.id,
              description:
                config.name +
                (config.description ? " - " + config.description : ""),
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

  // Load data on mount
  onMount(async () => {
    await Promise.all([
      load_available_embedding_models(),
      loadExtractorConfigs(),
      loadChunkerConfigs(),
      loadEmbeddingConfigs(),
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

  async function create_rag_config() {
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
            extractor_config_id: selected_extractor_config_id,
            chunker_config_id: selected_chunker_config_id,
            embedding_config_id: selected_embedding_config_id,
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
  subtitle="A configuration for searching your docs, including extracting, chunking and embeddings."
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
                description="Split your documents into smaller chunks for search."
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
                description="Embedding models convert your document chunks into vectors for similarity search."
                info_description="Embedding models are a type of AI model which create searchable vectors from your chunks."
                fancy_select_options={embedding_options}
                bind:value={selected_embedding_config_id}
                inputType="fancy_select"
              />
            {/if}
          </div>
        </div>

        <!-- Advanced -->
        <Collapse title="Advanced Options">
          <FormElement
            label="Search Tool Name"
            description="A name to identify this tool. Leave blank and we'll generate one for you."
            optional={true}
            inputType="input"
            id="rag_config_name"
            bind:value={name}
          />
          <FormElement
            label="Description"
            description="A description of the search tool for your reference."
            optional={true}
            inputType="textarea"
            id="rag_config_description"
            bind:value={description}
          />
        </Collapse>
      </FormContainer>
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={show_create_extractor_dialog}
  title="Create Extractor"
  width="wide"
  on:close={() => {
    handle_modal_close()
    if (selected_extractor_config_id === "create_new") {
      selected_extractor_config_id = null
    }
  }}
>
  <div class="font-light text-sm mb-4">
    Extractors are used to convert your documents into text.
  </div>

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
  title="Create Chunker"
  width="wide"
  on:close={() => {
    handle_modal_close()
    if (selected_chunker_config_id === "create_new") {
      selected_chunker_config_id = null
    }
  }}
>
  <div class="font-light text-sm">
    Chunkers are used to split your documents into smaller pieces for better
    retrieval.
  </div>

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
  title="Create Embedding Configuration"
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
