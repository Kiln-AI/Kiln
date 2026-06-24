<script lang="ts">
  import type {
    EvalConfigType,
    AvailableModels,
  } from "$lib/types"
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import { get_provider_image } from "$lib/ui/provider_image"
  import { available_models } from "$lib/stores"

  export let task_id: string

  export let model_name: string | undefined = undefined
  export let provider_name: string | undefined = undefined
  export let combined_model_name: string | undefined = undefined
  export let selected_algo: EvalConfigType | undefined = undefined

  const evaluator_algorithms: {
    id: EvalConfigType
    name: string
    description: string
  }[] = [
    {
      id: "llm_as_judge",
      name: "LLM as Judge",
      description:
        "The model selected above will be asked to judge task outputs.",
    },
    {
      id: "g_eval",
      name: "G-Eval Judge",
      description:
        "A more advanced LLM-as-Judge method which considers token probabilities for more precise scores.",
    },
  ]

  type SuggestedModel = {
    model_name: string
    provider_name: string
    model_id: string
    provider_id: string
  }

  const provider_id_preferred_order = [
    "openai",
    "gemini_api",
    "vertex",
    "anthropic",
    "groq",
    "openrouter",
    "ollama",
  ]

  function build_suggested_models(
    providers: AvailableModels[],
  ): SuggestedModel[] {
    const suggested: SuggestedModel[] = []

    for (const provider of providers) {
      for (const model of provider.models) {
        if (model.suggested_for_evals) {
          const existing_model_index = suggested.findIndex(
            (s) => s.model_id === model.id,
          )

          if (existing_model_index !== -1) {
            const existing_model = suggested[existing_model_index]
            const current_provider_preference =
              provider_id_preferred_order.indexOf(provider.provider_id)
            const existing_provider_preference =
              provider_id_preferred_order.indexOf(existing_model.provider_id)

            const current_priority =
              current_provider_preference === -1
                ? Infinity
                : current_provider_preference
            const existing_priority =
              existing_provider_preference === -1
                ? Infinity
                : existing_provider_preference

            if (current_priority < existing_priority) {
              suggested[existing_model_index] = {
                model_name: model.name,
                model_id: model.id,
                provider_id: provider.provider_id,
                provider_name: provider.provider_name,
              }
            }
          } else {
            suggested.push({
              model_name: model.name,
              model_id: model.id,
              provider_id: provider.provider_id,
              provider_name: provider.provider_name,
            })
          }
        }
      }
    }

    return suggested
  }
  $: suggested_models = build_suggested_models($available_models || [])
  let force_select_dropdown = false

  $: unsupported_algos = update_unsupported_algos_and_default_algo(
    $available_models,
    model_name,
    provider_name,
  )
  function update_unsupported_algos_and_default_algo(
    avail_models: AvailableModels[],
    mn: string | undefined,
    pn: string | undefined,
  ): Record<string, string> {
    const model_info = avail_models
      .find((m) => m.provider_id === pn)
      ?.models.find((m) => m.id === mn)
    if (!model_info) {
      selected_algo = undefined
      return {}
    }

    if (model_info.supports_logprobs) {
      selected_algo = "g_eval"
      return {}
    }

    selected_algo = "llm_as_judge"
    return {
      g_eval:
        "G-Eval requires logprobs which do not work with this model or provider.",
    }
  }

  function select_evaluator(algo: EvalConfigType) {
    selected_algo = algo
  }
</script>

<div class="flex flex-col gap-6">
  <div class="text-sm font-medium text-left flex flex-col gap-1">
    <div class="text-xl font-bold">Select Judge Model</div>
    <div class="text-xs text-gray-500">
      Specify which model will be used for the judge. This is not necessarily
      the model that will be used to run the task.
    </div>
  </div>

  {#if !model_name && !force_select_dropdown && suggested_models.length > 0}
    <div>
      <div class="font-light text-lg text-gray-500 mb-2">
        Recommended Models:
      </div>
      <div class="flex flex-wrap flex-row gap-4">
        {#each suggested_models as model}
          {@const provider_image = get_provider_image(model.provider_id)}
          <button
            class="card card-bordered border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 w-[200px] aspect-[5/6] p-4 flex flex-col justify-center items-center text-center group cursor-pointer"
            on:click={() => {
              model_name = model.model_name
              provider_name = model.provider_name
              combined_model_name = `${model.provider_id}/${model.model_id}`
            }}
          >
            <div class="flex flex-col gap-3 items-center">
              <img
                src={provider_image}
                class="w-10 h-10"
                alt={model.provider_name}
              />
              <div class="flex flex-col gap-1">
                <div class="font-medium text-sm leading-tight">
                  {model.model_name}
                </div>
                <div class="text-xs text-gray-500">
                  {model.provider_name}
                </div>
              </div>
            </div>
          </button>
        {/each}
      </div>
      <div class="font-light text-lg text-gray-500 mt-8 mb-2">
        Other Available Models:
      </div>
      <div class="flex flex-row gap-2">
        <button
          class="btn btn-outline btn-wide"
          on:click={() => (force_select_dropdown = true)}
        >
          Browse All Models
        </button>
      </div>
    </div>
  {:else}
    <AvailableModelsDropdown
      {task_id}
      bind:model={combined_model_name}
      bind:model_name
      bind:provider_name
      settings={{
        requires_structured_output: selected_algo !== "g_eval",
        requires_logprobs: selected_algo === "g_eval",
        suggested_mode: "evals",
      }}
    />
  {/if}

  {#if model_name}
    <div>
      <div class="text-xl font-bold mb-2">Select Judge Algorithm</div>

      <div class="form-control flex flex-row gap-4 flex-wrap">
        {#each evaluator_algorithms as algo}
          {@const is_unsupported = !!unsupported_algos[algo.id]}
          {#if !is_unsupported}
            <label class="label cursor-pointer">
              <div
                class="card card-bordered border-base-300 shadow-md flex flex-col gap-2 p-6 hover:shadow-lg hover:border-primary/50 transition-all duration-200 w-[260px] aspect-[5/6]"
              >
                <div class="flex flex-col gap-2 text-center items-center">
                  <input
                    type="radio"
                    name="radio-evaluator"
                    class="radio checked:bg-primary mx-auto my-8"
                    checked={selected_algo === algo.id}
                    disabled={is_unsupported}
                    on:change={() => select_evaluator(algo.id)}
                  />
                  <div class="font-medium text-lg">
                    {algo.name}
                  </div>
                  <div class="text-sm font-light text-gray-500">
                    {algo.description}
                  </div>
                </div>
              </div>
            </label>
          {/if}
        {/each}
      </div>
    </div>
  {/if}

</div>
