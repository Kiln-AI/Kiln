<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createEventDispatcher } from "svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { number_validator } from "$lib/utils/input_validators"
  import type {
    ChunkerType,
    CreateChunkerConfigRequest,
    EmbeddingConfig,
  } from "$lib/types"
  import CreateEmbeddingForm from "./create_embedding_form.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { embedding_model_name, provider_name_from_id } from "$lib/stores"
  import { chunker_type_format } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string = ""
  let description: string = ""
  let chunk_size: number = 512
  let chunk_overlap: number = 64
  let chunker_type: ChunkerType = "fixed_window"

  // Semantic chunker state
  let buffer_size: number = 3
  let breakpoint_percentile_threshold: number = 95
  let embedding_configs: EmbeddingConfig[] = []
  let selected_embedding_config_id: string | null = null
  let show_create_embedding_dialog: Dialog | null = null

  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { chunker_config_id: string }
  }>()

  async function load_embedding_configs() {
    try {
      const { error: fetch_error, data } = await client.GET(
        "/api/projects/{project_id}/embedding_configs",
        {
          params: { path: { project_id } },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      embedding_configs = data
    } catch (e) {
      error = createKilnError(e)
    }
  }

  $: if (chunker_type === "semantic" && embedding_configs.length === 0) {
    // lazy-load when user selects semantic
    load_embedding_configs()
  }

  // Build embedding fancy select options like the RAG page
  $: embedding_options = [
    {
      options: [
        {
          label: "New Embedding Configuration",
          value: "create_new",
          badge: "＋",
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
                `${embedding_model_name(
                  config.model_name,
                  config.model_provider_name,
                )} (${provider_name_from_id(config.model_provider_name)})` +
                (config.properties?.dimensions
                  ? ` - ${config.properties?.dimensions} dimensions`
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

  // Open/close create embedding dialog when selecting special option
  $: if (selected_embedding_config_id === "create_new") {
    show_create_embedding_dialog?.show()
  } else {
    show_create_embedding_dialog?.close()
  }

  function build_validate_create_chunker_config_body(): CreateChunkerConfigRequest {
    switch (chunker_type) {
      case "fixed_window":
        return {
          name: name || null,
          description: description || null,
          chunker_type: "fixed_window" as ChunkerType,
          properties: {
            chunk_size,
            chunk_overlap,
          },
        }
      case "semantic":
        if (!selected_embedding_config_id) {
          throw new Error("Please select or create an embedding config")
        }
        return {
          name: name || null,
          description: description || null,
          chunker_type: "semantic" as ChunkerType,
          properties: {
            embedding_config_id: selected_embedding_config_id,
            buffer_size,
            breakpoint_percentile_threshold,
          },
        }
      default: {
        // trigger a type error if there is a new chunker type, but don't handle it
        // in the switch
        const exhaustiveCheck: never = chunker_type
        return exhaustiveCheck
      }
    }
  }

  async function create_chunker_config() {
    try {
      loading = true

      const { error: create_chunker_error, data } = await client.POST(
        "/api/projects/{project_id}/create_chunker_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: build_validate_create_chunker_config_body(),
        },
      )

      if (create_chunker_error) {
        throw create_chunker_error
      }

      dispatch("success", { chunker_config_id: data.id || "" })
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }
</script>

<FormContainer
  submit_visible={true}
  submit_label="Create Chunker"
  on:submit={async () => {
    await create_chunker_config()
  }}
  {error}
  gap={4}
  bind:submitting={loading}
  {keyboard_submit}
>
  <div class="flex flex-col gap-4">
    <FormElement
      label="Chunker Type"
      description="The technique to use to split text into smaller chunks."
      info_description="Fixed Window splits by size, while Semantic splits by meaning using semantic similarity to group sentences together."
      inputType="fancy_select"
      id="chunker_type"
      bind:value={chunker_type}
      fancy_select_options={[
        {
          options: [
            {
              label: chunker_type_format("fixed_window"),
              value: "fixed_window",
              description: "Simple size-based chunks",
            },
            {
              label: chunker_type_format("semantic"),
              value: "semantic",
              description: "Split by meaning using semantic similarity",
            },
          ],
        },
      ]}
    />

    {#if chunker_type === "fixed_window"}
      <FormElement
        label="Chunk Size"
        description="The approximate number of words to include in each chunk."
        info_description="Smaller chunks allow for more granular search, but may not encapsulate the broader context."
        inputType="input_number"
        id="chunk_size"
        bind:value={chunk_size}
        validator={number_validator({
          min: 1,
          integer: true,
          label: "Chunk Size",
          optional: true,
        })}
      />
      <FormElement
        label="Chunk Overlap"
        description="The number of words to overlap between chunks."
        info_description="Without overlap, sentences that span chunk boundaries can be lost because they aren’t fully contained in any chunk."
        inputType="input_number"
        id="chunk_overlap"
        bind:value={chunk_overlap}
        validator={number_validator({
          min: 0,
          integer: true,
          label: "Chunk Overlap",
          optional: true,
        })}
      />
    {/if}

    {#if chunker_type === "semantic"}
      <FormElement
        id="embedding_select"
        label="Embedding Model"
        description="Embedding models convert sentences into semantic vectors that are compared to find where topics end and begin."
        info_description="Embedding models are a type of AI model which create searchable vectors from text."
        fancy_select_options={embedding_options}
        bind:value={selected_embedding_config_id}
        inputType="fancy_select"
      />

      <FormElement
        label="Buffer Size"
        description="The number of sentences to group together when evaluating semantic similarity."
        info_description="Set to 1 to consider each sentence individually, or set to > 1 to group sentences together."
        inputType="input_number"
        id="buffer_size"
        bind:value={buffer_size}
        validator={number_validator({
          min: 3,
          integer: true,
          label: "Buffer Size (Sentences)",
          optional: false,
        })}
      />
      <FormElement
        label="Breakpoint Percentile"
        description="The percentile of cosine dissimilarity that must be exceeded between a group of sentences and the next to create a breakpoint."
        info_description="The smaller this number is, the more chunks will be generated."
        inputType="input_number"
        id="breakpoint_percentile_threshold"
        bind:value={breakpoint_percentile_threshold}
        validator={number_validator({
          min: 0,
          max: 100,
          integer: true,
          label: "Breakpoint Percentile (0 - 100)",
          optional: false,
        })}
      />
    {/if}
  </div>

  {#if chunker_type === "semantic"}
    <Dialog
      bind:this={show_create_embedding_dialog}
      title="Embedding Configuration"
      subtitle="Convert text chunks into vectors for similarity search."
      width="normal"
      on:close={() => {
        if (selected_embedding_config_id === "create_new") {
          selected_embedding_config_id = null
        }
      }}
    >
      <CreateEmbeddingForm
        keyboard_submit={true}
        on:success={async (e) => {
          await load_embedding_configs()
          selected_embedding_config_id = e.detail.embedding_config_id
        }}
      />
    </Dialog>
  {/if}

  <Collapse title="Advanced Options">
    <FormElement
      label="Chunker Name"
      description="A name to identify this chunker. Leave blank and we'll generate one for you."
      optional={true}
      inputType="input"
      id="name"
      bind:value={name}
    />
    <FormElement
      label="Description"
      description="A description of the chunker for you and your team. This will have no effect on the chunker's behavior."
      optional={true}
      inputType="textarea"
      id="description"
      bind:value={description}
    />
  </Collapse>
</FormContainer>
