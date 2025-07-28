<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import Warning from "$lib/ui/warning.svelte"
  import AvailableModelsDropdown from "../../../../../run/available_models_dropdown.svelte"
  import type { Eval, Task, EvalConfigType } from "$lib/types"
  import { tick } from "svelte"
  import { load_task } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { get_eval_steps } from "./eval_steps_utils"
  import Collapse from "$lib/ui/collapse.svelte"
  import type { AvailableModels } from "$lib/types"
  import { available_models, load_available_models } from "$lib/stores"
  import { get_provider_image } from "$lib/ui/provider_image"
  import posthog from "posthog-js"

  let combined_model_name: string | undefined = undefined
  let model_name: string | undefined = undefined
  let provider_name: string | undefined = undefined
  let task_description: string = ""
  let eval_steps: string[] = []

  let evaluator: Eval | undefined = undefined
  let task: Task | null = null

  // Loading
  let loading_eval = true
  let loading_eval_error: KilnError | undefined = undefined
  let loading_task = true
  let loading_task_error: KilnError | undefined = undefined
  $: loading = loading_eval || loading_task
  $: loading_error = loading_eval_error || loading_task_error
  onMount(async () => {
    // tick: need to wait for the page params to be available
    await tick()
    await load_eval()
    await load_task_local()
    await load_available_models()
    // Force these back to undefined -- we don't want to take the last-used model from the available model dropdown
    model_name = undefined
    provider_name = undefined
    combined_model_name = undefined
  })

  async function load_task_local() {
    if (!evaluator) {
      loading_error = createKilnError(
        new Error("Evaluator not loaded, can not load task"),
      )
      return
    }
    try {
      loading_task = true
      task = await load_task($page.params.project_id, $page.params.task_id)
      if (!task) {
        throw new Error("Task not found")
      }

      // Setup the evaluator template for a task requirements (if template is task requirements)
      if (evaluator?.template === "kiln_requirements") {
        eval_steps = []
        for (const requirement of task.requirements) {
          eval_steps.push(
            `Does the model's output align to the following requirement: ${requirement.name}\nRequirement Instruction: ${requirement.instruction}\nRequirement Priority (0 is highest, 3 is lowest): ${requirement.priority}`,
          )
        }
        eval_steps.push(
          "Given prior thinking and priorities, what would be an appropriate overall score for this task, from 1 to 5, with 1 being the worst and 5 being the best?",
        )
      }
      eval_steps = get_eval_steps(evaluator?.template, task, evaluator)

      // Use the task instruction as the task description starter point
      task_description = task.instruction
    } catch (e) {
      loading_task_error = createKilnError(e)
    } finally {
      loading_task = false
    }
  }

  async function load_eval() {
    try {
      loading_eval = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
              task_id: $page.params.task_id,
              eval_id: $page.params.eval_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      evaluator = data
    } catch (e) {
      loading_eval_error = createKilnError(e)
    } finally {
      loading_eval = false
    }
  }

  let selected_algo: EvalConfigType | undefined = undefined

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

  function select_evaluator(algo: EvalConfigType) {
    selected_algo = algo
  }

  let create_evaluator_error: KilnError | null = null
  let create_evaluator_loading = false
  let complete = false
  async function create_evaluator() {
    try {
      if (!selected_algo) {
        throw new Error("No evaluator algorithm selected")
      }
      if (!model_name || !provider_name) {
        throw new Error("No model selected")
      }
      create_evaluator_loading = true

      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/create_eval_config",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
              task_id: $page.params.task_id,
              eval_id: $page.params.eval_id,
            },
          },
          body: {
            type: selected_algo,
            model_name: model_name,
            // @ts-expect-error provider is not typed, but server will validate
            provider: provider_name,
            properties: {
              // @ts-expect-error properties are not typed, but server will validate
              eval_steps: eval_steps,
              // @ts-expect-error properties are not typed, but server will validate
              task_description: task_description,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      posthog.capture("create_eval_config", {
        algo: selected_algo,
        model_name: model_name,
        provider_name: provider_name,
      })
      complete = true
      const next_page = $page.url.searchParams.get("next_page")
      if (next_page === "eval_configs") {
        goto(
          `/evals/${$page.params.project_id}/${$page.params.task_id}/${$page.params.eval_id}/eval_configs`,
        )
      } else {
        goto(
          `/evals/${$page.params.project_id}/${$page.params.task_id}/${$page.params.eval_id}?selected_eval_config=${data.id}`,
        )
      }
    } catch (e) {
      create_evaluator_error = createKilnError(e)
    } finally {
      create_evaluator_loading = false
    }
  }

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
            // Found a duplicate model_id, check provider preference
            const existing_model = suggested[existing_model_index]
            const current_provider_preference =
              provider_id_preferred_order.indexOf(provider.provider_id)
            const existing_provider_preference =
              provider_id_preferred_order.indexOf(existing_model.provider_id)

            // If current provider is more preferred (lower index), replace the existing model
            // Handle case where provider is not in preference list (treat as lowest priority)
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
            // If existing provider is more preferred, continue to next model
          } else {
            // No duplicate found, add the model
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
    available_models: AvailableModels[],
    model_name: string | undefined,
    provider_name: string | undefined,
  ): Record<string, string> {
    const model_info = available_models
      .find((m) => m.provider_id === provider_name)
      ?.models.find((m) => m.id === model_name)
    if (!model_info) {
      selected_algo = undefined
      return {}
    }

    // Select G-Eval if the model supports logprobs
    if (model_info.supports_logprobs) {
      selected_algo = "g_eval"
      return {}
    }

    // Otherwise, default to LLM as Judge
    selected_algo = "llm_as_judge"
    return {
      g_eval:
        "G-Eval requires logprobs which do not work with this model or provider.",
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Add a Judge"
    subtitle="A judge evaluates task outputs with a model, evaluation prompt, and algorithm."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.getkiln.ai/docs/evaluations#finding-the-ideal-eval-method"
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task Information</div>
        <div class="text-error text-sm">
          {loading_error?.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else}
      <FormContainer
        submit_visible={!!(selected_algo && combined_model_name)}
        submit_label="Create Judge"
        on:submit={create_evaluator}
        bind:error={create_evaluator_error}
        bind:submitting={create_evaluator_loading}
        warn_before_unload={!complete && !!selected_algo}
      >
        <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
          <div class="text-xl font-bold" id="requirements_part">
            Step 1: Select Judge Model
          </div>
          <div class="text-xs text-gray-500">
            Specify which model will be used for the judge. This is not
            necessarily the model that will be used to run the task.
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
            bind:model={combined_model_name}
            bind:model_name
            bind:provider_name
            requires_structured_output={selected_algo !== "g_eval"}
            requires_logprobs={selected_algo === "g_eval"}
            suggested_mode="evals"
          />
        {/if}

        {#if model_name}
          <div>
            <div class="text-xl font-bold mt-6 mb-2">
              Step 2: Select Judge Algorithm
            </div>

            <div class="form-control flex flex-row gap-4 flex-wrap">
              {#each evaluator_algorithms as evaluator}
                {@const is_unsupported = !!unsupported_algos[evaluator.id]}
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
                          checked={selected_algo === evaluator.id}
                          disabled={is_unsupported}
                          on:change={() => select_evaluator(evaluator.id)}
                        />
                        <div class="font-medium text-lg">
                          {evaluator.name}
                        </div>
                        <div class="text-sm font-light text-gray-500">
                          {evaluator.description}
                        </div>
                      </div>
                    </div>
                  </label>
                {/if}
              {/each}
            </div>
          </div>
        {/if}

        {#if selected_algo && combined_model_name}
          <div class="mt-2"></div>
          <Collapse title="Advanced: Prompts and Instructions" small={false}>
            <div>
              <Warning
                warning_message="Customizing the prompts and thinking steps used by the evaluator can improve the quality of the eval. We've pre-populated steps based on your task and eval."
                warning_color="success"
                warning_icon="info"
              />
            </div>
            <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
              <div class="text-xl font-bold" id="requirements_part">
                Step 3: Task Description
              </div>
              <div class="text-xs text-gray-500">
                <div>
                  Include a short description of what this task does. The
                  evaluator will use this for context. Keep it short, ideally
                  one or two sentences. Include requirements for the eval below,
                  not in this description.
                </div>
              </div>
            </div>
            <FormElement
              label=""
              inputType="textarea"
              id="task_description"
              optional={true}
              bind:value={task_description}
            />

            <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
              <div class="text-xl font-bold" id="requirements_part">
                Step 4: Evaluation Instructions
              </div>
              <div class="text-xs text-gray-500">
                This is a list of instructions to be used by the evaluator's
                model. It will 'think' through each of these steps in order
                before generating final scores.
              </div>
              {#if evaluator?.template}
                <div class="text-xs text-gray-500">
                  We've pre-populated the evaluation steps for you based on the
                  template you selected ({evaluator.template}). Feel free to
                  edit.
                </div>
              {/if}
            </div>

            <FormList
              bind:content={eval_steps}
              content_label="Evaluation Step"
              empty_content={""}
              let:item_index
            >
              <FormElement
                label="Model Instructions"
                inputType="textarea"
                id="eval_step_{item_index}"
                hide_label={true}
                bind:value={eval_steps[item_index]}
              />
            </FormList>
          </Collapse>
        {/if}
      </FormContainer>
    {/if}
  </AppPage>
</div>
