<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { createEventDispatcher, onMount } from "svelte"
  import type {
    EmbeddingModelDetails,
    EmbeddingModelName,
    EmbeddingProvider,
    ModelProviderName,
  } from "$lib/types"
  import Collapse from "$lib/ui/collapse.svelte"
  import { number_validator } from "$lib/utils/input_validators"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string = ""
  let description: string = ""
  let selectedModel: EmbeddingOptionValue | null = null
  let customDimensions: number | null = null
  let embeddingModels: OptionGroup[] = []
  let loadingModels = true
  export let keyboard_submit: boolean = false

  type EmbeddingOptionValue = {
    model_name: EmbeddingModelName
    model_provider_name: ModelProviderName
    n_dimensions: number | null
    max_input_tokens: number | null
    supports_custom_dimensions: boolean | null
  }

  const dispatch = createEventDispatcher<{
    success: { embedding_config_id: string }
  }>()

  onMount(async () => {
    await loadEmbeddingModels()
  })

  async function loadEmbeddingModels() {
    try {
      loadingModels = true
      const { error: modelsError, data } = await client.GET(
        "/api/available_embedding_models",
      )

      if (modelsError) {
        error = createKilnError(modelsError)
        return
      }

      // Transform the API response into OptionGroup format
      embeddingModels = data
        .filter((provider: EmbeddingProvider) => provider.models.length > 0)
        .map((provider: EmbeddingProvider) => ({
          label: provider.provider_name,
          options: provider.models.map((model: EmbeddingModelDetails) => ({
            label: model.name,
            value: {
              model_name: model.id,
              model_provider_name: provider.provider_id,
              n_dimensions: model.n_dimensions,
              max_input_tokens: model.max_input_tokens,
              supports_custom_dimensions: model.supports_custom_dimensions,
              suggested_for_chunk_embedding:
                model.suggested_for_chunk_embedding,
            },
            badge: model.suggested_for_chunk_embedding
              ? "Recommended"
              : undefined,
            description: `${model.n_dimensions} dimensions${model.max_input_tokens ? ` • ${model.max_input_tokens.toLocaleString()} max tokens` : ""}`,
          })),
        }))
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loadingModels = false
    }
  }

  async function create_embedding_config() {
    if (!selectedModel) {
      error = createKilnError(new Error("Please select an embedding model"))
      return
    }

    try {
      loading = true

      const properties: Record<string, string | number | boolean> = {}
      if (customDimensions && selectedModel.supports_custom_dimensions) {
        properties.dimensions = customDimensions
      }

      const { error: create_embedding_error, data } = await client.POST(
        "/api/projects/{project_id}/create_embedding_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name || null,
            description: description || null,
            model_provider_name:
              selectedModel.model_provider_name as ModelProviderName,
            model_name: selectedModel.model_name as EmbeddingModelName,
            properties,
          },
        },
      )

      if (create_embedding_error) {
        error = createKilnError(create_embedding_error)
        return
      }

      if (!data.id) {
        error = createKilnError(new Error("Failed to create embedding config"))
        return
      }

      dispatch("success", { embedding_config_id: data.id })
    } finally {
      loading = false
    }
  }
</script>

<FormContainer
  submit_visible={true}
  submit_label="Create Embedding Config"
  on:submit={async () => {
    await create_embedding_config()
  }}
  {error}
  gap={4}
  bind:submitting={loading}
  {keyboard_submit}
>
  <div class="flex flex-col gap-4">
    {#if loadingModels}
      <div class="flex items-center gap-2">
        <div class="loading loading-spinner loading-sm"></div>
        <span>Loading embedding models...</span>
      </div>
    {:else}
      <FormElement
        label="Embedding Model"
        description="The embedding model to use to convert your text into vectors."
        info_description="An embedding is a vector representation of text that can be used for similarity search."
        inputType="fancy_select"
        fancy_select_options={embeddingModels}
        bind:value={selectedModel}
        id="embedding_model"
      />
    {/if}
  </div>
  <Collapse title="Advanced Options">
    <FormElement
      label="Embedding Config Name"
      description="A name to identify this embedding config. Leave blank and we'll generate one for you."
      optional={true}
      inputType="input"
      id="name"
      bind:value={name}
    />
    <FormElement
      label="Description"
      description="A description of the embedding config for you and your team. This will have no effect on the embedding config's behavior."
      optional={true}
      inputType="textarea"
      id="description"
      bind:value={description}
    />

    {#if selectedModel && selectedModel.supports_custom_dimensions}
      <FormElement
        label="Custom Embedding Dimensions"
        description="Leave blank to use the default, or set a custom embedding size."
        info_description="This controls the size of the vector embedding which is generated. Leave blank for the default unless you understand how to tune this."
        optional={true}
        inputType="input_number"
        id="custom_dimensions"
        bind:value={customDimensions}
        validator={number_validator({
          min: 1,
          max: selectedModel.n_dimensions || undefined,
          integer: true,
          label: "Custom Dimensions",
          optional: true,
        })}
      />
    {/if}
  </Collapse>
</FormContainer>
