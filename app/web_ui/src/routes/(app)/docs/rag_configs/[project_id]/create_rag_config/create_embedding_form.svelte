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
  } from "../../../../../../lib/types"
  import Warning from "../../../../../../lib/ui/warning.svelte"
  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string | null = null
  let description: string = ""
  let selectedModel: EmbeddingOptionValue | null = null
  let customDimensions: number | null = null
  let embeddingModels: OptionGroup[] = []
  let loadingModels = true

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
            },
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
      const selectedModelData = selectedModel

      const properties: Record<string, string | number | boolean> = {}
      if (customDimensions && selectedModelData.supports_custom_dimensions) {
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
              selectedModelData.model_provider_name as ModelProviderName,
            model_name: selectedModelData.model_name as EmbeddingModelName,
            properties,
          },
        },
      )

      if (create_embedding_error) {
        error = createKilnError(create_embedding_error)
        return
      }

      dispatch("success", { embedding_config_id: data.id || "" })
    } finally {
      loading = false
    }
  }
</script>

<FormContainer
  submit_visible={true}
  submit_label="Create Embedding Config"
  on:submit={create_embedding_config}
  {error}
  gap={4}
  bind:submitting={loading}
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
        description="Select an embedding model to use for generating embeddings."
        inputType="fancy_select"
        fancy_select_options={embeddingModels}
        bind:value={selectedModel}
        id="embedding_model"
      />

      {#if selectedModel && selectedModel.supports_custom_dimensions}
        <Warning
          warning_message="This model supports custom dimensions. You can override the default number of dimensions for this model. Leave blank to use the default."
          warning_color="gray"
        />
        <FormElement
          label="Custom Dimensions"
          description="Override the default number of dimensions for this model. Leave blank to use the default."
          optional={true}
          inputType="input_number"
          id="custom_dimensions"
          bind:value={customDimensions}
        />
      {/if}
    {/if}
  </div>
  <div class="mt-4">
    <div class="collapse collapse-arrow bg-base-200">
      <input type="checkbox" class="peer" />
      <div class="collapse-title font-medium">Advanced Options</div>
      <div class="collapse-content flex flex-col gap-4">
        <FormElement
          label="Embedding Config Name"
          description="Leave blank and we'll generate one for you."
          optional={true}
          inputType="input"
          id="embedding_config_name"
          bind:value={name}
        />
        <FormElement
          label="Description"
          description="A description of the embedding config for you and your team. This will have no effect on the embedding config's behavior."
          optional={true}
          inputType="textarea"
          id="embedding_config_description"
          bind:value={description}
        />
      </div>
    </div>
  </div>
</FormContainer>
