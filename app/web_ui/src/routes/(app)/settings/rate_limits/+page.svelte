<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { provider_name_from_id } from "$lib/stores"
  import FormElement from "$lib/utils/form_element.svelte"

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
    [provider: string]: {
      [model: string]: number
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

  let provider_apply_values: { [provider: string]: number | null } = {}

  let rate_limits_version = 0

  let model_inputs: { [key: string]: number | null } = {}

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
      rate_limits = (limits_data as RateLimits) || {}

      group_models_by_provider()
    } catch (e) {
      load_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  function group_models_by_provider() {
    if (!all_models) return

    normal_models_by_provider = group_by_provider(all_models.normal_models)
    embedding_models_by_provider = group_by_provider(
      all_models.embedding_models,
    )
    reranker_models_by_provider = group_by_provider(all_models.reranker_models)

    model_inputs = {}
    for (const model of all_models.normal_models) {
      const key = getModelInputKey(model.provider_name, model.model_name)
      model_inputs[key] = get_rate_limit(model.provider_name, model.model_name)
    }
    for (const model of all_models.embedding_models) {
      const key = getModelInputKey(model.provider_name, model.model_name)
      model_inputs[key] = get_rate_limit(model.provider_name, model.model_name)
    }
    for (const model of all_models.reranker_models) {
      const key = getModelInputKey(model.provider_name, model.model_name)
      model_inputs[key] = get_rate_limit(model.provider_name, model.model_name)
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

  function get_rate_limit(provider: string, model: string): number | null {
    return rate_limits[provider]?.[model] ?? null
  }

  function set_rate_limit(
    provider: string,
    model: string,
    value: number | null,
  ) {
    const newRateLimits = { ...rate_limits }

    if (!newRateLimits[provider]) {
      newRateLimits[provider] = {}
    } else {
      newRateLimits[provider] = { ...newRateLimits[provider] }
    }

    if (value === null || value === 0) {
      delete newRateLimits[provider][model]
      if (Object.keys(newRateLimits[provider]).length === 0) {
        delete newRateLimits[provider]
      }
    } else {
      newRateLimits[provider][model] = value
    }

    rate_limits = newRateLimits
  }

  function apply_to_provider(provider: string, models: ModelInfo[]) {
    const value = provider_apply_values[provider]
    if (value !== null && value !== undefined) {
      const newRateLimits = { ...rate_limits }

      if (!newRateLimits[provider]) {
        newRateLimits[provider] = {}
      } else {
        newRateLimits[provider] = { ...newRateLimits[provider] }
      }

      for (const model of models) {
        const inputKey = getModelInputKey(provider, model.model_name)
        if (value === 0) {
          delete newRateLimits[provider][model.model_name]
          model_inputs[inputKey] = null
        } else {
          newRateLimits[provider][model.model_name] = value
          model_inputs[inputKey] = value
        }
      }

      if (Object.keys(newRateLimits[provider]).length === 0) {
        delete newRateLimits[provider]
      }

      rate_limits = newRateLimits
      rate_limits_version++
      provider_apply_values[provider] = null
    }
  }

  function getModelInputKey(provider: string, model: string): string {
    return `${provider}::${model}`
  }

  function syncModelInputsToRateLimits() {
    for (const [key, value] of Object.entries(model_inputs)) {
      const [provider, model] = key.split("::")
      const currentLimit = get_rate_limit(provider, model)
      if (value !== currentLimit) {
        set_rate_limit(provider, model, value)
      }
    }
  }

  $: {
    if (Object.keys(model_inputs).length > 0) {
      syncModelInputsToRateLimits()
    }
  }

  async function save_rate_limits_handler() {
    try {
      saving = true
      save_success = false
      save_error = null

      const { error: api_error } = await client.POST("/api/rate_limits", {
        body: rate_limits,
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
      <!-- Normal Models -->
      {#if Object.keys(normal_models_by_provider).length > 0}
        <div class="space-y-4">
          <h2 class="text-xl font-semibold text-gray-800">LLMs</h2>
          {#each Object.keys(normal_models_by_provider).sort() as provider}
            {@const models = normal_models_by_provider[provider]}
            <details
              class="collapse collapse-arrow bg-base-100 border border-gray-200"
            >
              <summary class="collapse-title text-base font-medium">
                {provider_name_from_id(provider)}
              </summary>
              <div class="collapse-content">
                <div class="flex gap-2 items-center mb-3 mt-2">
                  <div class="flex-1">
                    <FormElement
                      inputType="input_number"
                      id="apply_all_{provider}"
                      label="Apply to all models"
                      bind:value={provider_apply_values[provider]}
                      placeholder="e.g., 5"
                      optional={true}
                      light_label={true}
                    />
                  </div>
                  <button
                    class="btn btn-sm btn-outline mt-6"
                    on:click={() => apply_to_provider(provider, models)}
                    disabled={!provider_apply_values[provider]}
                  >
                    Apply
                  </button>
                </div>

                <div class="space-y-3 mt-4">
                  {#each models as model (model.model_name + rate_limits_version)}
                    {@const inputKey = getModelInputKey(
                      provider,
                      model.model_name,
                    )}
                    {@const modelLimit = get_rate_limit(
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
                      placeholder="Unlimited"
                      optional={true}
                      light_label={true}
                    />
                  {/each}
                </div>
              </div>
            </details>
          {/each}
        </div>
      {/if}

      <!-- Embedding Models -->
      {#if Object.keys(embedding_models_by_provider).length > 0}
        <div class="space-y-4">
          <h2 class="text-xl font-semibold text-gray-800">Embedding Models</h2>
          {#each Object.keys(embedding_models_by_provider).sort() as provider}
            {@const models = embedding_models_by_provider[provider]}
            <details
              class="collapse collapse-arrow bg-base-100 border border-gray-200"
            >
              <summary class="collapse-title text-base font-medium">
                {provider_name_from_id(provider)}
              </summary>
              <div class="collapse-content">
                <div class="flex gap-2 items-center mb-3 mt-2">
                  <div class="flex-1">
                    <FormElement
                      inputType="input_number"
                      id="apply_all_{provider}"
                      label="Apply to all models"
                      bind:value={provider_apply_values[provider]}
                      placeholder="e.g., 5"
                      optional={true}
                      light_label={true}
                    />
                  </div>
                  <button
                    class="btn btn-sm btn-outline mt-6"
                    on:click={() => apply_to_provider(provider, models)}
                    disabled={!provider_apply_values[provider]}
                  >
                    Apply
                  </button>
                </div>

                <div class="space-y-3 mt-4">
                  {#each models as model (model.model_name + rate_limits_version)}
                    {@const inputKey = getModelInputKey(
                      provider,
                      model.model_name,
                    )}
                    {@const modelLimit = get_rate_limit(
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
                      placeholder="Unlimited"
                      optional={true}
                      light_label={true}
                    />
                  {/each}
                </div>
              </div>
            </details>
          {/each}
        </div>
      {/if}

      <!-- Reranker Models -->
      {#if Object.keys(reranker_models_by_provider).length > 0}
        <div class="space-y-4">
          <h2 class="text-xl font-semibold text-gray-800">Reranker Models</h2>
          {#each Object.keys(reranker_models_by_provider).sort() as provider}
            {@const models = reranker_models_by_provider[provider]}
            <details
              class="collapse collapse-arrow bg-base-100 border border-gray-200"
            >
              <summary class="collapse-title text-base font-medium">
                {provider_name_from_id(provider)}
              </summary>
              <div class="collapse-content">
                <div class="flex gap-2 items-center mb-3 mt-2">
                  <div class="flex-1">
                    <FormElement
                      inputType="input_number"
                      id="apply_all_{provider}"
                      label="Apply to all models"
                      bind:value={provider_apply_values[provider]}
                      placeholder="e.g., 5"
                      optional={true}
                      light_label={true}
                    />
                  </div>
                  <button
                    class="btn btn-sm btn-outline mt-6"
                    on:click={() => apply_to_provider(provider, models)}
                    disabled={!provider_apply_values[provider]}
                  >
                    Apply
                  </button>
                </div>

                <div class="space-y-3 mt-4">
                  {#each models as model (model.model_name + rate_limits_version)}
                    {@const inputKey = getModelInputKey(
                      provider,
                      model.model_name,
                    )}
                    {@const modelLimit = get_rate_limit(
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
                      placeholder="Unlimited"
                      optional={true}
                      light_label={true}
                    />
                  {/each}
                </div>
              </div>
            </details>
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
