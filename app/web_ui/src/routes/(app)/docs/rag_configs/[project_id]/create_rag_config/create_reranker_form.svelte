<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { createEventDispatcher, onMount } from "svelte"
  import type {
    ModelProviderName,
    RerankerModelDetails,
    RerankerProvider,
  } from "$lib/types"
  import Collapse from "$lib/ui/collapse.svelte"
  import { number_validator } from "$lib/utils/input_validators"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let loadingRerankers = true
  let error: KilnError | null = null

  let name: string = ""
  let description: string = ""
  let selectedReranker: RerankerOptionValue | null = null
  let top_n: number = 5
  let rerankerModels: OptionGroup[] = []
  export let keyboard_submit: boolean = false

  type RerankerOptionValue = {
    model_name: string
    model_provider_name: ModelProviderName
  }

  const dispatch = createEventDispatcher<{
    success: { reranker_config_id: string }
  }>()

  onMount(async () => {
    await loadRerankerModels()
  })

  async function loadRerankerModels() {
    try {
      loadingRerankers = true
      const { error: load_models_error, data } = await client.GET(
        "/api/available_reranker_models",
      )

      if (load_models_error) {
        throw load_models_error
      }

      // Transform the API response into OptionGroup format
      rerankerModels = data
        .filter((provider: RerankerProvider) => provider.models.length > 0)
        .map((provider: RerankerProvider) => ({
          label: provider.provider_name,
          options: provider.models.map((model: RerankerModelDetails) => ({
            label: model.name,
            value: {
              model_name: model.id,
              model_provider_name: provider.provider_id,
            },
          })),
        }))
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loadingRerankers = false
    }
  }

  async function create_reranker_config() {
    try {
      error = null
      loading = true

      if (!selectedReranker) {
        throw new Error("Please select a reranker model")
      }

      const { error: create_reranker_error, data } = await client.POST(
        "/api/projects/{project_id}/create_reranker_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name || null,
            description: description || null,
            top_n: top_n,
            model_provider_name:
              selectedReranker.model_provider_name as ModelProviderName,
            model_name: selectedReranker.model_name,
            properties: {
              type: "cohere_compatible",
            },
          },
        },
      )

      if (create_reranker_error) {
        throw create_reranker_error
      }

      if (!data.id) {
        throw new Error("Failed to create reranker config")
      }

      dispatch("success", { reranker_config_id: data.id })
      error = null
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }
</script>

{#if loading || loadingRerankers}
  <div class="flex flex-col gap-4">
    <div class="flex justify-center items-center gap-2">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  </div>
{:else}
  <FormContainer
    submit_visible={true}
    submit_label="Create Reranker Config"
    on:submit={async () => {
      await create_reranker_config()
    }}
    {error}
    gap={4}
    bind:submitting={loading}
    {keyboard_submit}
  >
    <div class="flex flex-col gap-4">
      <FormElement
        label="Reranker Model"
        description="The reranker model to use to rerank your search results."
        info_description="Reranker models are a type of AI model which rerank search results."
        inputType="fancy_select"
        fancy_select_options={rerankerModels}
        bind:value={selectedReranker}
        id="reranker_model"
      />

      <FormElement
        label="Top N"
        description="The number of results to return from the reranker."
        info_description="This controls the number of results to return from the reranker."
        inputType="input_number"
        id="top_n"
        bind:value={top_n}
        validator={number_validator({
          min: 1,
          integer: true,
          label: "Top N",
        })}
      />
    </div>
    <Collapse title="Advanced Options">
      <FormElement
        label="Reranker Config Name"
        description="A name to identify this reranker config. Leave blank and we'll generate one for you."
        optional={true}
        inputType="input"
        id="name"
        bind:value={name}
      />
      <FormElement
        label="Description"
        description="A description of the reranker config for you and your team. This will have no effect on the reranker config's behavior."
        optional={true}
        inputType="textarea"
        id="description"
        bind:value={description}
      />
    </Collapse>
  </FormContainer>
{/if}
