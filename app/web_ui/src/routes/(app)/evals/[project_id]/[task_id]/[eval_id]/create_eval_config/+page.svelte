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
  import type { Eval, EvalTemplateId, Task, EvalConfigType } from "$lib/types"
  import { tick } from "svelte"
  import { load_task } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { _ } from "svelte-i18n"

  let combined_model_name: string | undefined = undefined
  let model_name: string | undefined = undefined
  let provider_name: string | undefined = undefined
  let task_description: string = ""
  let eval_steps: string[] = []

  type EvalTemplateWithoutKiln = Exclude<EvalTemplateId, "kiln_requirements">

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
  })

  async function load_task_local() {
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
          $_(
            "evaluation.create_eval_config.eval_templates.kiln_requirements_suffix",
          ),
        )
      }

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

      // Load static template eval steps if we have one
      if (evaluator.template && evaluator.template !== "kiln_requirements") {
        // Use one of the static templates from i18n
        const templateSteps = $_(
          `evaluation.create_eval_config.eval_templates.${evaluator.template}`,
        )
        if (Array.isArray(templateSteps)) {
          eval_steps = templateSteps
        }
      }
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
    warning: string | undefined
  }[] = [
    {
      id: "g_eval",
      name: $_("evaluation.create_eval_config.algorithms.g_eval.name"),
      description: $_(
        "evaluation.create_eval_config.algorithms.g_eval.description",
      ),
      warning: $_("evaluation.create_eval_config.algorithms.g_eval.warning"),
    },
    {
      id: "llm_as_judge",
      name: $_("evaluation.create_eval_config.algorithms.llm_as_judge.name"),
      description: $_(
        "evaluation.create_eval_config.algorithms.llm_as_judge.description",
      ),
      warning: undefined,
    },
  ]

  function select_evaluator(algo: EvalConfigType) {
    selected_algo = algo

    // Force the user to look at the supported model list in the dropdown. Unsupported models are very unlikely to work.
    // dispatch so the model dropdown renders first, and doesn't overwrite this
    setTimeout(() => {
      combined_model_name = undefined
    }, 0)
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
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("evaluation.create_eval_config.title")}
    subtitle={$_("evaluation.create_eval_config.subtitle")}
    sub_subtitle={$_("evaluation.create_eval_config.sub_subtitle")}
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
        <div class="font-medium">
          {$_("evaluation.create_eval_config.error_loading_task")}
        </div>
        <div class="text-error text-sm">
          {loading_error?.getMessage() || $_("errors.unknown_error")}
        </div>
      </div>
    {:else}
      <FormContainer
        submit_visible={!!(selected_algo && combined_model_name)}
        submit_label={$_("evaluation.create_eval_config.create_eval_method")}
        on:submit={create_evaluator}
        bind:error={create_evaluator_error}
        bind:submitting={create_evaluator_loading}
        warn_before_unload={!complete && !!selected_algo}
      >
        <div class="text-xl font-bold">
          {$_("evaluation.create_eval_config.step1_title")}
        </div>

        <div class="form-control flex flex-col gap-2">
          {#each evaluator_algorithms as evaluator}
            <label class="label cursor-pointer">
              <div
                class="card card-bordered border-base-300 bg-base-200 shadow-md w-full flex flex-row gap-2 p-4"
              >
                <div
                  class="w-14 flex-none flex place-content-center place-items-center"
                >
                  <input
                    type="radio"
                    name="radio-evaluator"
                    class="radio checked:bg-primary"
                    checked={selected_algo === evaluator.id}
                    on:change={() => select_evaluator(evaluator.id)}
                  />
                </div>
                <div class="flex flex-col gap-2">
                  <div class="font-medium">
                    {evaluator.name}
                  </div>
                  <div>
                    {evaluator.description}
                  </div>
                  <Warning
                    warning_message={evaluator.warning}
                    warning_color="warning"
                    tight={true}
                  />
                </div>
              </div>
            </label>
          {/each}
        </div>

        {#if selected_algo}
          <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
            <div class="text-xl font-bold" id="requirements_part">
              {$_("evaluation.create_eval_config.step2_title")}
            </div>
            <div class="text-xs text-gray-500">
              {$_("evaluation.create_eval_config.step2_desc")}
            </div>
          </div>

          <AvailableModelsDropdown
            bind:model={combined_model_name}
            bind:model_name
            bind:provider_name
            requires_structured_output={selected_algo !== "g_eval"}
            requires_logprobs={selected_algo === "g_eval"}
            suggested_mode="evals"
          />
        {/if}

        {#if selected_algo && combined_model_name}
          <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
            <div class="text-xl font-bold" id="requirements_part">
              {$_("evaluation.create_eval_config.step3_title")}
            </div>
            <div class="text-xs text-gray-500">
              <div>
                {$_("evaluation.create_eval_config.step3_desc")}
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
              {$_("evaluation.create_eval_config.step4_title")}
            </div>
            <div class="text-xs text-gray-500">
              {$_("evaluation.create_eval_config.step4_desc")}
            </div>
            {#if evaluator?.template}
              <div class="text-xs text-gray-500">
                {$_("evaluation.create_eval_config.template_prepopulated", {
                  values: { template: evaluator.template },
                })}
              </div>
            {/if}
          </div>

          <FormList
            bind:content={eval_steps}
            content_label={$_("evaluation.evaluation_steps")}
            empty_content={""}
            let:item_index
          >
            <FormElement
              label={$_("evaluation.instructions")}
              inputType="textarea"
              id="eval_step_{item_index}"
              hide_label={true}
              bind:value={eval_steps[item_index]}
            />
          </FormList>
        {/if}
      </FormContainer>
    {/if}
  </AppPage>
</div>
