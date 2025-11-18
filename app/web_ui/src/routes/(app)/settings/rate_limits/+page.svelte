<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { provider_name_from_id } from "$lib/stores"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"

  type ModelInfo = {
    model_name: string
    friendly_name: string
    provider_name: string
    model_id: string | null
  }

  type AllModelsResponse = {
    normal_models: ModelInfo[]
    embedding_models: ModelInfo[]
    reranker_models: ModelInfo[]
  }

  type RateLimits = {
    provider_limits?: { [provider: string]: number }
    model_limits?: {
      [provider: string]: {
        [model: string]: number
      }
    }
  }

  type ModelsByProvider = {
    [provider: string]: ModelInfo[]
  }

  let all_models: AllModelsResponse | null = null
  let rate_limits: RateLimits = {}
  let loading = true
  let load_error: KilnError | null = null
  let saving = false
  let save_error: KilnError | null = null
  let save_success = false

  let normal_models_by_provider: ModelsByProvider = {}
  let embedding_models_by_provider: ModelsByProvider = {}
  let reranker_models_by_provider: ModelsByProvider = {}

  let rate_limits_version = 0

  let model_inputs: { [key: string]: number | null } = {}
  let provider_inputs: { [provider: string]: number | null } = {}

  const load_data = async () => {
    try {
      loading = true
      load_error = null

      const { data: models_data, error: models_error } =
        await client.GET("/api/models/all")
      if (models_error) {
        throw models_error
      }
      if (!models_data) {
        throw new KilnError("Failed to load models", null)
      }
      all_models = models_data

      const { data: limits_data, error: limits_error } =
        await client.GET("/api/rate_limits")
      if (limits_error) {
        throw limits_error
      }
      rate_limits = normalize_rate_limits(limits_data)

      group_models_by_provider()
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
    if (!all_models) return

    normal_models_by_provider = group_by_provider(all_models.normal_models)
    embedding_models_by_provider = group_by_provider(
      all_models.embedding_models,
    )
    reranker_models_by_provider = group_by_provider(all_models.reranker_models)

    const all_providers = new Set<string>()
    model_inputs = {}
    provider_inputs = {}

    for (const model of all_models.normal_models) {
      all_providers.add(model.provider_name)
      const key = getModelInputKey(model.provider_name, model.model_name)
      model_inputs[key] = get_model_limit(model.provider_name, model.model_name)
    }
    for (const model of all_models.embedding_models) {
      all_providers.add(model.provider_name)
      const key = getModelInputKey(model.provider_name, model.model_name)
      model_inputs[key] = get_model_limit(model.provider_name, model.model_name)
    }
    for (const model of all_models.reranker_models) {
      all_providers.add(model.provider_name)
      const key = getModelInputKey(model.provider_name, model.model_name)
      model_inputs[key] = get_model_limit(model.provider_name, model.model_name)
    }

    for (const provider of all_providers) {
      provider_inputs[provider] = get_provider_limit(provider)
    }
  }

  function group_by_provider(models: ModelInfo[]): ModelsByProvider {
    const grouped: ModelsByProvider = {}
    for (const model of models) {
      if (!grouped[model.provider_name]) {
        grouped[model.provider_name] = []
      }
      grouped[model.provider_name].push(model)
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
      saving = true
      save_success = false
      save_error = null

      const { error: api_error } = await client.POST("/api/rate_limits", {
        body: rate_limits as Record<string, Record<string, number>>,
      })
      if (api_error) {
        throw api_error
      }

      save_success = true
      setTimeout(() => {
        save_success = false
      }, 3000)
    } catch (e) {
      save_error = createKilnError(e)
    } finally {
      saving = false
    }
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
      <div class="max-w-5xl space-y-8">
        <!-- LLMs -->
        {#if Object.keys(normal_models_by_provider).length > 0}
          <div class="space-y-4">
            <h2 class="text-xl font-semibold text-gray-800">LLMs</h2>
            {#each Object.keys(normal_models_by_provider).sort() as provider}
              {@const models = normal_models_by_provider[provider]}
              <Collapse title={provider_name_from_id(provider)}>
                <div class="space-y-4 mt-4">
                  <FormElement
                    inputType="input_number"
                    id="{provider}_provider_limit"
                    label="Provider-wide limit"
                    bind:value={provider_inputs[provider]}
                    placeholder="Unlimited"
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
                    <div class="space-y-3 mt-4">
                      {#each models as model (model.model_name + rate_limits_version)}
                        {@const inputKey = getModelInputKey(
                          provider,
                          model.model_name,
                        )}
                        {@const modelLimit = get_model_limit(
                          provider,
                          model.model_name,
                        )}
                        {#if model_inputs[inputKey] === undefined}
                          {((model_inputs[inputKey] = modelLimit), "")}
                        {/if}
                        <FormElement
                          inputType="input_number"
                          id="{provider}_{model.model_name}"
                          label={model.friendly_name}
                          bind:value={model_inputs[inputKey]}
                          placeholder={`Use provider limit (${provider_inputs[provider] ?? "Unlimited"})`}
                          optional={true}
                          light_label={true}
                        />
                      {/each}
                    </div>
                  </div>
                </div>
              </Collapse>
            {/each}
          </div>
        {/if}

        <!-- Embedding Models -->
        {#if Object.keys(embedding_models_by_provider).length > 0}
          <div class="space-y-4">
            <h2 class="text-xl font-semibold text-gray-800">
              Embedding Models
            </h2>
            {#each Object.keys(embedding_models_by_provider).sort() as provider}
              {@const models = embedding_models_by_provider[provider]}
              <Collapse title={provider_name_from_id(provider)}>
                <div class="space-y-4 mt-4">
                  <FormElement
                    inputType="input_number"
                    id="{provider}_provider_limit_embedding"
                    label="Provider-wide limit"
                    bind:value={provider_inputs[provider]}
                    placeholder="Unlimited"
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
                    <div class="space-y-3 mt-4">
                      {#each models as model (model.model_name + rate_limits_version)}
                        {@const inputKey = getModelInputKey(
                          provider,
                          model.model_name,
                        )}
                        {@const modelLimit = get_model_limit(
                          provider,
                          model.model_name,
                        )}
                        {#if model_inputs[inputKey] === undefined}
                          {((model_inputs[inputKey] = modelLimit), "")}
                        {/if}
                        <FormElement
                          inputType="input_number"
                          id="{provider}_{model.model_name}"
                          label={model.friendly_name}
                          bind:value={model_inputs[inputKey]}
                          placeholder={`Use provider limit (${provider_inputs[provider] ?? "Unlimited"})`}
                          optional={true}
                          light_label={true}
                        />
                      {/each}
                    </div>
                  </div>
                </div>
              </Collapse>
            {/each}
          </div>
        {/if}

        <!-- Reranker Models -->
        {#if Object.keys(reranker_models_by_provider).length > 0}
          <div class="space-y-4">
            <h2 class="text-xl font-semibold text-gray-800">Reranker Models</h2>
            {#each Object.keys(reranker_models_by_provider).sort() as provider}
              {@const models = reranker_models_by_provider[provider]}
              <Collapse title={provider_name_from_id(provider)}>
                <div class="space-y-4 mt-4">
                  <FormElement
                    inputType="input_number"
                    id="{provider}_provider_limit_reranker"
                    label="Provider-wide limit"
                    bind:value={provider_inputs[provider]}
                    placeholder="Unlimited"
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
                    <div class="space-y-3 mt-4">
                      {#each models as model (model.model_name + rate_limits_version)}
                        {@const inputKey = getModelInputKey(
                          provider,
                          model.model_name,
                        )}
                        {@const modelLimit = get_model_limit(
                          provider,
                          model.model_name,
                        )}
                        {#if model_inputs[inputKey] === undefined}
                          {((model_inputs[inputKey] = modelLimit), "")}
                        {/if}
                        <FormElement
                          inputType="input_number"
                          id="{provider}_{model.model_name}"
                          label={model.friendly_name}
                          bind:value={model_inputs[inputKey]}
                          placeholder={`Use provider limit (${provider_inputs[provider] ?? "Unlimited"})`}
                          optional={true}
                          light_label={true}
                        />
                      {/each}
                    </div>
                  </div>
                </div>
              </Collapse>
            {/each}
          </div>
        {/if}

        <!-- Save button and status -->
        <div class="flex items-center gap-4 pt-4">
          <button
            class="btn btn-primary"
            on:click={save_rate_limits_handler}
            disabled={saving}
          >
            {#if saving}
              <span class="loading loading-spinner loading-sm"></span>
            {/if}
            Save Rate Limits
          </button>

          {#if save_success}
            <div class="text-success font-medium">
              Rate limits saved successfully!
            </div>
          {/if}

          {#if save_error}
            <div class="text-error font-medium">
              Error: {save_error.message}
            </div>
          {/if}
        </div>
      </div>
    {/if}
  </AppPage>
</div>
