<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import {
    available_models as available_models_store,
    available_embedding_models as available_embedding_models_store,
    available_reranker_models as available_reranker_models_store,
    load_available_embedding_models,
    load_available_models,
    load_available_reranker_models,
    provider_name_from_id,
  } from "$lib/stores"
  import type {
    AvailableModels,
    EmbeddingProvider,
    RerankerProvider,
    ModelDetails,
    EmbeddingModelDetails,
    RerankerModelDetails,
  } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import Collapse from "$lib/ui/collapse.svelte"

  type RateLimits = {
    provider_limits?: { [provider: string]: number }
    model_limits?: {
      [provider: string]: {
        [model: string]: number
      }
    }
  }

  type ModelsByProvider = {
    [provider: string]: (
      | ModelDetails
      | EmbeddingModelDetails
      | RerankerModelDetails
    )[]
  }

  let rate_limits: RateLimits = {}
  let loading = true
  let load_error: KilnError | null = null
  let submitting = false
  let save_error: KilnError | null = null
  let saved = false

  let normal_models_by_provider: ModelsByProvider = {}
  let embedding_models_by_provider: ModelsByProvider = {}
  let reranker_models_by_provider: ModelsByProvider = {}

  let model_inputs: { [key: string]: number | null } = {}
  let provider_inputs: { [provider: string]: number | null } = {}

  let initial_model_inputs: { [key: string]: number | null } = {}
  let initial_provider_inputs: { [provider: string]: number | null } = {}

  $: has_changes =
    !saved &&
    (JSON.stringify(model_inputs) !== JSON.stringify(initial_model_inputs) ||
      JSON.stringify(provider_inputs) !==
        JSON.stringify(initial_provider_inputs))

  $: warn_before_unload = has_changes

  const load_data = async () => {
    try {
      loading = true
      load_error = null

      await Promise.all([
        load_available_models(),
        load_available_embedding_models(),
        load_available_reranker_models(),
      ])

      const limits_response = (await client.GET("/api/rate_limits")) as {
        data?: Record<string, unknown>
        error?: Error
      }

      if (limits_response.error) {
        throw limits_response.error
      }

      rate_limits = normalize_rate_limits(limits_response.data)

      group_models_by_provider()

      await tick()
      initial_model_inputs = { ...model_inputs }
      initial_provider_inputs = { ...provider_inputs }
    } catch (e) {
      load_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  function normalize_rate_limits(
    data: Record<string, unknown> | undefined,
  ): RateLimits {
    if (!data || typeof data !== "object") {
      return {
        provider_limits: {},
        model_limits: {},
      }
    }

    if ("provider_limits" in data || "model_limits" in data) {
      return {
        provider_limits: (data.provider_limits as Record<string, number>) || {},
        model_limits:
          (data.model_limits as Record<string, Record<string, number>>) || {},
      }
    }

    return {
      provider_limits: {},
      model_limits: data as Record<string, Record<string, number>>,
    }
  }

  function group_models_by_provider() {
    normal_models_by_provider = group_by_provider_from_list(
      $available_models_store,
    )
    embedding_models_by_provider = group_by_provider_from_embedding_list(
      $available_embedding_models_store,
    )
    reranker_models_by_provider = group_by_provider_from_reranker_list(
      $available_reranker_models_store,
    )

    const all_providers = new Set<string>()
    model_inputs = {}
    provider_inputs = {}

    for (const provider_group of $available_models_store) {
      if (provider_group.models.length === 0) {
        continue
      }
      all_providers.add(provider_group.provider_id)
      for (const model of provider_group.models) {
        const key = getModelInputKey(provider_group.provider_id, model.id)
        model_inputs[key] = get_model_limit(
          provider_group.provider_id,
          model.id,
        )
      }
    }

    for (const provider_group of $available_embedding_models_store) {
      if (provider_group.models.length === 0) {
        continue
      }
      all_providers.add(provider_group.provider_id)
      for (const model of provider_group.models) {
        const key = getModelInputKey(provider_group.provider_id, model.id)
        model_inputs[key] = get_model_limit(
          provider_group.provider_id,
          model.id,
        )
      }
    }

    for (const provider_group of $available_reranker_models_store) {
      if (provider_group.models.length === 0) {
        continue
      }
      all_providers.add(provider_group.provider_id)
      for (const model of provider_group.models) {
        const key = getModelInputKey(provider_group.provider_id, model.id)
        model_inputs[key] = get_model_limit(
          provider_group.provider_id,
          model.id,
        )
      }
    }

    for (const provider of all_providers) {
      provider_inputs[provider] = get_provider_limit(provider)
    }
  }

  function group_by_provider_from_list(
    provider_list: AvailableModels[],
  ): ModelsByProvider {
    const grouped: ModelsByProvider = {}
    for (const provider_group of provider_list) {
      if (provider_group.models.length === 0) {
        continue
      }
      if (!grouped[provider_group.provider_id]) {
        grouped[provider_group.provider_id] = []
      }
      grouped[provider_group.provider_id].push(...provider_group.models)
    }
    return grouped
  }

  function group_by_provider_from_embedding_list(
    provider_list: EmbeddingProvider[],
  ): ModelsByProvider {
    const grouped: ModelsByProvider = {}
    for (const provider_group of provider_list) {
      if (provider_group.models.length === 0) {
        continue
      }
      if (!grouped[provider_group.provider_id]) {
        grouped[provider_group.provider_id] = []
      }
      grouped[provider_group.provider_id].push(...provider_group.models)
    }
    return grouped
  }

  function group_by_provider_from_reranker_list(
    provider_list: RerankerProvider[],
  ): ModelsByProvider {
    const grouped: ModelsByProvider = {}
    for (const provider_group of provider_list) {
      if (provider_group.models.length === 0) {
        continue
      }
      if (!grouped[provider_group.provider_id]) {
        grouped[provider_group.provider_id] = []
      }
      grouped[provider_group.provider_id].push(...provider_group.models)
    }
    return grouped
  }

  function get_provider_limit(provider: string): number | null {
    return rate_limits.provider_limits?.[provider] ?? null
  }

  function get_model_limit(provider: string, model: string): number | null {
    return rate_limits.model_limits?.[provider]?.[model] ?? null
  }

  function set_provider_limit(provider: string, value: number | null) {
    const newRateLimits = { ...rate_limits }
    if (!newRateLimits.provider_limits) {
      newRateLimits.provider_limits = {}
    } else {
      newRateLimits.provider_limits = { ...newRateLimits.provider_limits }
    }

    if (value === null || value === 0) {
      delete newRateLimits.provider_limits[provider]
    } else {
      newRateLimits.provider_limits[provider] = value
    }

    rate_limits = newRateLimits
  }

  function set_model_limit(
    provider: string,
    model: string,
    value: number | null,
  ) {
    const newRateLimits = { ...rate_limits }

    if (!newRateLimits.model_limits) {
      newRateLimits.model_limits = {}
    }

    if (!newRateLimits.model_limits[provider]) {
      newRateLimits.model_limits[provider] = {}
    } else {
      newRateLimits.model_limits[provider] = {
        ...newRateLimits.model_limits[provider],
      }
    }

    if (value === null || value === 0) {
      delete newRateLimits.model_limits[provider][model]
      if (Object.keys(newRateLimits.model_limits[provider]).length === 0) {
        delete newRateLimits.model_limits[provider]
      }
    } else {
      newRateLimits.model_limits[provider][model] = value
    }

    rate_limits = newRateLimits
  }

  function getModelInputKey(provider: string, model: string): string {
    return `${provider}::${model}`
  }

  function syncInputsToRateLimits() {
    for (const [provider, value] of Object.entries(provider_inputs)) {
      const currentLimit = get_provider_limit(provider)
      if (value !== currentLimit) {
        set_provider_limit(provider, value)
      }
    }

    for (const [key, value] of Object.entries(model_inputs)) {
      const [provider, model] = key.split("::")
      const currentLimit = get_model_limit(provider, model)
      if (value !== currentLimit) {
        set_model_limit(provider, model, value)
      }
    }
  }

  $: {
    if (
      Object.keys(model_inputs).length > 0 ||
      Object.keys(provider_inputs).length > 0
    ) {
      syncInputsToRateLimits()
    }
  }

  async function save_rate_limits_handler() {
    try {
      save_error = null
      saved = false

      const { error: api_error } = await client.POST("/api/rate_limits", {
        body: rate_limits as Record<string, Record<string, number>>,
      })
      if (api_error) {
        throw api_error
      }

      saved = true
      await tick()
      initial_model_inputs = { ...model_inputs }
      initial_provider_inputs = { ...provider_inputs }
    } catch (e) {
      save_error = createKilnError(e)
    } finally {
      submitting = false
    }
  }

  function is_custom_model_provider(provider: string): boolean {
    return provider === "kiln_custom_registry" || provider === "kiln_fine_tune"
  }

  onMount(async () => {
    await load_data()
  })
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Rate Limits"
    sub_subtitle="Configure max concurrent requests for models to manage API rate limits."
    breadcrumbs={[{ label: "Settings", href: "/settings" }]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if load_error}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="alert alert-error">
          <span>{load_error.message}</span>
        </div>
      </div>
    {:else}
      <FormContainer
        submit_label="Save Rate Limits"
        on:submit={save_rate_limits_handler}
        bind:submitting
        bind:saved
        bind:warn_before_unload
        error={save_error}
        focus_on_mount={false}
      >
        <!-- LLMs -->
        <div class="space-y-4">
          <h2 class="text-xl font-semibold text-gray-800">LLMs</h2>
          {#if Object.keys(normal_models_by_provider).length > 0}
            {#each Object.keys(normal_models_by_provider).sort((a, b) => {
              if (is_custom_model_provider(a)) return 1
              if (is_custom_model_provider(b)) return -1
              return a.localeCompare(b)
            }) as provider}
              {@const models = normal_models_by_provider[provider]}
              <Collapse title={provider_name_from_id(provider)}>
                <div class="space-y-4 mt-4">
                  <FormElement
                    inputType="input_number"
                    id="{provider}_provider_limit"
                    label="Provider-wide limit"
                    bind:value={provider_inputs[provider]}
                    placeholder="Default"
                    optional={true}
                    light_label={true}
                    description="Max concurrent requests for all models from this provider. If no model-specific limit is set for the model, this limit will be used."
                  />

                  <div class="border-l-2 pl-4">
                    <FormElement
                      id="model_specific_limits"
                      label="Model-specific limits"
                      inputType="header_only"
                      value=""
                      light_label={true}
                      description="Max concurrent requests for individual models from this provider. If no model-specific limit is set for the model, the provider-wide limit will be used."
                    />
                    {#if models.length === 0}
                      <div class="text-sm text-gray-500 mt-4">
                        No models available for this provider.
                      </div>
                    {:else}
                      <div class="space-y-3 mt-4">
                        {#each models as model (model.id)}
                          {@const inputKey = getModelInputKey(
                            provider,
                            model.id,
                          )}
                          {@const modelLimit = get_model_limit(
                            provider,
                            model.id,
                          )}
                          {#if model_inputs[inputKey] === undefined}
                            {((model_inputs[inputKey] = modelLimit), "")}
                          {/if}
                          <FormElement
                            inputType="input_number"
                            id="{provider}_{model.id}"
                            label={model.name}
                            bind:value={model_inputs[inputKey]}
                            placeholder={`Use provider limit (${provider_inputs[provider] ?? "Default"})`}
                            optional={true}
                            light_label={true}
                          />
                        {/each}
                      </div>
                    {/if}
                  </div>
                </div>
              </Collapse>
            {/each}
          {:else}
            <div class="space-y-4">
              <div class="text-sm text-gray-500 mt-4">
                No LLMs available. <a href="/settings/providers"
                  >Connect an AI provider</a
                > to get started.
              </div>
            </div>
          {/if}
        </div>

        <!-- Embedding Models -->
        <div class="space-y-4">
          <h2 class="text-xl font-semibold text-gray-800">Embedding Models</h2>

          {#if Object.keys(embedding_models_by_provider).length > 0}
            {#each Object.keys(embedding_models_by_provider).sort((a, b) => {
              if (is_custom_model_provider(a)) return 1
              if (is_custom_model_provider(b)) return -1
              return a.localeCompare(b)
            }) as provider}
              {@const models = embedding_models_by_provider[provider]}
              <Collapse title={provider_name_from_id(provider)}>
                <div class="space-y-4 mt-4">
                  <FormElement
                    inputType="input_number"
                    id="{provider}_provider_limit_embedding"
                    label="Provider-wide limit"
                    bind:value={provider_inputs[provider]}
                    placeholder="Default"
                    optional={true}
                    light_label={true}
                    description="Max concurrent requests for all models from this provider. If no model-specific limit is set for the model, this limit will be used."
                  />

                  <div class="border-l-2 pl-4">
                    <FormElement
                      id="model_specific_limits"
                      label="Model-specific limits"
                      inputType="header_only"
                      value=""
                      light_label={true}
                      description="Max concurrent requests for individual models from this provider. If no model-specific limit is set for the model, the provider-wide limit will be used."
                    />
                    {#if models.length === 0}
                      <div class="text-sm text-gray-500 mt-4">
                        No models available for this provider.
                      </div>
                    {:else}
                      <div class="space-y-3 mt-4">
                        {#each models as model (model.id)}
                          {@const inputKey = getModelInputKey(
                            provider,
                            model.id,
                          )}
                          {@const modelLimit = get_model_limit(
                            provider,
                            model.id,
                          )}
                          {#if model_inputs[inputKey] === undefined}
                            {((model_inputs[inputKey] = modelLimit), "")}
                          {/if}
                          <FormElement
                            inputType="input_number"
                            id="{provider}_{model.id}"
                            label={model.name}
                            bind:value={model_inputs[inputKey]}
                            placeholder={`Use provider limit (${provider_inputs[provider] ?? "Default"})`}
                            optional={true}
                            light_label={true}
                          />
                        {/each}
                      </div>
                    {/if}
                  </div>
                </div>
              </Collapse>
            {/each}
          {:else}
            <div class="space-y-4">
              <div class="text-sm text-gray-500 mt-4">
                No embedding models available. <a href="/settings/providers"
                  >Connect an AI provider</a
                > to get started.
              </div>
            </div>
          {/if}
        </div>

        <!-- Reranker Models -->
        <div class="space-y-4">
          <h2 class="text-xl font-semibold text-gray-800">Reranker Models</h2>
          {#if Object.keys(reranker_models_by_provider).length > 0}
            {#each Object.keys(reranker_models_by_provider).sort((a, b) => {
              if (is_custom_model_provider(a)) return 1
              if (is_custom_model_provider(b)) return -1
              return a.localeCompare(b)
            }) as provider}
              {@const models = reranker_models_by_provider[provider]}
              <Collapse title={provider_name_from_id(provider)}>
                <div class="space-y-4 mt-4">
                  <FormElement
                    inputType="input_number"
                    id="{provider}_provider_limit_reranker"
                    label="Provider-wide limit"
                    bind:value={provider_inputs[provider]}
                    placeholder="Default"
                    optional={true}
                    light_label={true}
                    description="Max concurrent requests for all models from this provider. If no model-specific limit is set for the model, this limit will be used."
                  />

                  <div class="border-l-2 pl-4">
                    <FormElement
                      id="model_specific_limits"
                      label="Model-specific limits"
                      inputType="header_only"
                      value=""
                      light_label={true}
                      description="Max concurrent requests for individual models from this provider. If no model-specific limit is set for the model, the provider-wide limit will be used."
                    />
                    {#if models.length === 0}
                      <div class="text-sm text-gray-500 mt-4">
                        No models available for this provider.
                      </div>
                    {:else}
                      <div class="space-y-3 mt-4">
                        {#each models as model (model.id)}
                          {@const inputKey = getModelInputKey(
                            provider,
                            model.id,
                          )}
                          {@const modelLimit = get_model_limit(
                            provider,
                            model.id,
                          )}
                          {#if model_inputs[inputKey] === undefined}
                            {((model_inputs[inputKey] = modelLimit), "")}
                          {/if}
                          <FormElement
                            inputType="input_number"
                            id="{provider}_{model.id}"
                            label={model.name}
                            bind:value={model_inputs[inputKey]}
                            placeholder={`Use provider limit (${provider_inputs[provider] ?? "Default"})`}
                            optional={true}
                            light_label={true}
                          />
                        {/each}
                      </div>
                    {/if}
                  </div>
                </div>
              </Collapse>
            {/each}
          {:else}
            <div class="space-y-4">
              <div class="text-sm text-gray-500 mt-4">
                No reranker models available. <a href="/settings/providers"
                  >Connect an AI provider</a
                > to get started.
              </div>
            </div>
          {/if}
        </div>
      </FormContainer>
    {/if}
  </AppPage>
</div>
