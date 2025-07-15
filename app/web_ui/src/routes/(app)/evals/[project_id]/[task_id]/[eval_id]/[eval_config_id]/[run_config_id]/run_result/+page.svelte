<script lang="ts">
  import AppPage from "../../../../../../../app_page.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type {
    EvalRunResult,
    Eval,
    EvalConfig,
    EvalRun,
    TaskRunConfig,
  } from "$lib/types"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import { eval_config_to_ui_name } from "$lib/utils/formatters"
  import {
    model_info,
    load_model_info,
    model_name,
    provider_name_from_id,
    prompt_name_from_id,
    current_task_prompts,
    load_available_prompts,
    load_available_models,
  } from "$lib/stores"
  import OutputTypeTablePreview from "../../../output_type_table_preview.svelte"

  let results: EvalRunResult | null = null
  let results_error: KilnError | null = null
  let results_loading = true
  let peek_dialog: Dialog | null = null
  let thinking_dialog: Dialog | null = null
  let displayed_result: EvalRun | null = null

  onMount(async () => {
    peek_dialog?.show()
    // Wait for params to load
    await tick()
    // Wait for these 3 to load, as they are needed for better labels. Usually already cached and instant.
    await Promise.all([
      load_model_info(),
      load_available_prompts(),
      load_available_models(),
    ])
    get_evals()
  })

  async function get_evals() {
    try {
      results_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results",
        {
          params: {
            path: {
              project_id: $page.params.project_id,
              task_id: $page.params.task_id,
              eval_id: $page.params.eval_id,
              eval_config_id: $page.params.eval_config_id,
              run_config_id: $page.params.run_config_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      results = data
    } catch (error) {
      results_error = createKilnError(error)
    } finally {
      results_loading = false
    }
  }

  function get_run_config_properties(
    run_config: TaskRunConfig | null,
    evaluator: Eval | null,
  ): Record<string, string> {
    if (!run_config || !evaluator) {
      return {}
    }
    return {
      "Run Method Name": run_config.name,
      Model: model_name(
        run_config.run_config_properties?.model_name,
        $model_info,
      ),
      Provider: provider_name_from_id(
        run_config.run_config_properties?.model_provider_name,
      ),
      Prompt: prompt_name_from_id(
        run_config.run_config_properties?.prompt_id,
        $current_task_prompts,
      ),
      "Task Inputs From Dataset": evaluator.eval_set_filter_id,
    }
  }

  function get_eval_properties(
    evaluator: Eval | null,
    eval_config: EvalConfig | null,
  ): Record<string, string> {
    if (!evaluator || !eval_config) {
      return {}
    }
    return {
      "Judge Name": eval_config.name,
      "Judge Algorithm": eval_config_to_ui_name(eval_config.config_type),
      "Judge Model": model_name(eval_config.model_name, $model_info),
      "Model Provider": provider_name_from_id(eval_config.model_provider),
    }
  }
</script>

<AppPage
  title="Eval Results"
  subtitle="Evaluating a task run method with a judge."
>
  {#if results_loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if results_error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Eval Results</div>
      <div class="text-error text-sm">
        {results_error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if results && results.results.length === 0}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Eval Results Empty</div>
      <div class="text-error text-sm">
        No results found for this run method.
      </div>
    </div>
  {:else if results}
    <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
      <div class="grow basis-1/2">
        <div class="text-xl font-bold">Task Run Method</div>
        <div class="text-sm text-gray-500 mb-4">
          How the task outputs were generated.
        </div>
        <div
          class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
        >
          {#each Object.entries(get_run_config_properties(results.run_config, results.eval)) as [prop_name, prop_value]}
            <div class="flex items-center">{prop_name}</div>
            <div class="flex items-center text-gray-500 overflow-x-hidden">
              {prop_value}
            </div>
          {/each}
        </div>
      </div>
      <div class="grow basis-1/2">
        <div class="text-xl font-bold">Judge</div>
        <div class="text-sm text-gray-500 mb-4">
          The judge used to evaluate the task outputs.
        </div>
        <div
          class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
        >
          {#each Object.entries(get_eval_properties(results.eval, results.eval_config)) as [prop_name, prop_value]}
            <div class="flex items-center">{prop_name}</div>
            <div class="flex items-center text-gray-500 overflow-x-hidden">
              {prop_value}
            </div>
          {/each}
        </div>
      </div>
    </div>
    <div class="overflow-x-auto rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th>Input & Output</th>
            <th>Thinking</th>
            {#each results.eval.output_scores as score}
              <th class="text-center">
                {score.name}
                <OutputTypeTablePreview output_score_type={score.type} />
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each results.results as result}
            <tr>
              <td>
                <div class="font-medium">Input:</div>
                <div>
                  {result.input}
                </div>
                <div class="font-medium mt-4">Output:</div>
                <div>
                  {result.output}
                </div>
              </td>
              <td>
                {#if result.intermediate_outputs?.reasoning || result.intermediate_outputs?.chain_of_thought}
                  <div class="max-w-[600px] min-w-[200px]">
                    <div class="max-h-[140px] overflow-y-hidden relative">
                      {result.intermediate_outputs?.reasoning ||
                        result.intermediate_outputs?.chain_of_thought ||
                        "N/A"}
                      <div class="absolute bottom-0 left-0 w-full">
                        <div
                          class="h-36 bg-gradient-to-t from-white to-transparent"
                        ></div>
                        <div
                          class="text-center bg-white font-medium font-sm text-gray-500"
                        >
                          <button
                            class="text-gray-500"
                            on:click={() => {
                              displayed_result = result
                              thinking_dialog?.show()
                            }}
                          >
                            See all
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                {:else}
                  N/A
                {/if}
              </td>
              {#each results.eval.output_scores as score}
                {@const score_value =
                  result.scores[string_to_json_key(score.name)]}
                <td class="text-center">
                  {score_value != null ? score_value.toFixed(2) : "N/A"}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</AppPage>

<Dialog
  title="Are you sure you want to peek?"
  bind:this={peek_dialog}
  blur_background={true}
  action_buttons={[
    {
      label: "Look Anyways",
      isError: true,
    },
    {
      label: "Go Back",
      isPrimary: true,
      action: () => {
        window.history.back()
        return true
      },
    },
  ]}
>
  <div class="font-light flex flex-col gap-4">
    <Warning
      warning_message="We strongly suggest you don't look at these results! Looking at these results can bias future iteration."
    />
    <div>
      Viewing these evaluation results may lead to data leakage - a fundamental
      issue in machine learning where information from your test set
      inadvertently influences your development process. When you examine
      specific examples, you're likely to optimize for those particular cases
      rather than developing solutions that generalize well to unseen data.
    </div>
    <div>
      Use our "Run" screen or fresh synthetic dataset generation if you want to
      explore what type of content a run method is generating.
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={thinking_dialog}
  title="Thinking Output"
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  <div class="font-light text-sm whitespace-pre-wrap">
    {displayed_result?.intermediate_outputs?.reasoning ||
      displayed_result?.intermediate_outputs?.chain_of_thought ||
      "N/A"}
  </div>
</Dialog>
