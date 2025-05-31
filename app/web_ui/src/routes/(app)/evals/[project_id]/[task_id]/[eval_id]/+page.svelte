<script lang="ts">
  import { _ } from "svelte-i18n"
  import AppPage from "../../../../app_page.svelte"
  import type { Eval } from "$lib/types"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import type { EvalProgress } from "$lib/types"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import { eval_config_to_ui_name } from "$lib/utils/formatters"
  import {
    model_info,
    load_model_info,
    model_name,
    prompt_name_from_id,
    current_task_prompts,
  } from "$lib/stores"
  import type { ProviderModels, PromptResponse } from "$lib/types"
  import { goto } from "$app/navigation"
  import { prompt_link } from "$lib/utils/link_builder"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"

  import EditDialog from "$lib/ui/edit_dialog.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: eval_id = $page.params.eval_id

  let evaluator: Eval | null = null
  let eval_error: KilnError | null = null
  let eval_loading = true

  let eval_progress_loading = true
  let eval_progress: EvalProgress | null = null
  let eval_progress_error: KilnError | null = null

  $: loading = eval_loading || eval_progress_loading
  $: error = eval_error || eval_progress_error

  onMount(async () => {
    // Wait for page params to load
    await tick()
    // can be async
    load_model_info()
    // Load data in parallel
    await Promise.all([get_eval(), get_eval_progress()])
  })

  async function get_eval() {
    try {
      eval_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      evaluator = data
    } catch (error) {
      eval_error = createKilnError(error)
    } finally {
      eval_loading = false
    }
  }

  async function get_eval_progress() {
    eval_progress = null
    eval_progress_loading = true
    try {
      eval_progress = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/progress",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      eval_progress = data
    } catch (error) {
      eval_progress_error = createKilnError(error)
    } finally {
      eval_progress_loading = false
    }
  }

  type UiProperty = {
    name: string
    value: string
    tooltip?: string
    link?: string
  }

  function get_eval_properties(
    evaluator: Eval,
    eval_progress: EvalProgress | null,
    modelInfo: ProviderModels | null,
    taskPrompts: PromptResponse | null,
  ): UiProperty[] {
    const properties: UiProperty[] = []

    properties.push({
      name: $_("evaluation.main_page.name"),
      value: evaluator.name,
    })
    if (evaluator.description) {
      properties.push({
        name: $_("evaluation.main_page.description"),
        value: evaluator.description,
      })
    }
    properties.push({
      name: $_("evaluation.main_page.id"),
      value: evaluator.id || "unknown",
    })

    let eval_set_size = ""
    if (eval_progress) {
      eval_set_size = " (" + eval_progress.dataset_size + " items)"
    }
    properties.push({
      name: $_("evaluation.main_page.eval_dataset"),
      value: evaluator.eval_set_filter_id + eval_set_size,
      link: link_from_filter_id(evaluator.eval_set_filter_id),
    })
    let golden_dataset_size = ""
    if (eval_progress) {
      golden_dataset_size = " (" + eval_progress.golden_dataset_size + " items)"
    }
    properties.push({
      name: $_("evaluation.main_page.golden_dataset"),
      value: evaluator.eval_configs_filter_id + golden_dataset_size,
      tooltip: $_("evaluation.main_page.golden_dataset_tooltip"),
      link: link_from_filter_id(evaluator.eval_configs_filter_id),
    })

    if (eval_progress?.current_eval_method) {
      properties.push({
        name: $_("evaluation.main_page.eval_algorithm"),
        value: eval_config_to_ui_name(
          eval_progress.current_eval_method.config_type,
        ),
        tooltip: $_("evaluation.main_page.eval_algorithm_tooltip"),
      })
      properties.push({
        name: $_("evaluation.main_page.eval_model"),
        value: model_name(
          eval_progress.current_eval_method.model_name,
          modelInfo,
        ),
        tooltip: $_("evaluation.main_page.eval_model_tooltip"),
      })
    }

    if (eval_progress?.current_run_method) {
      properties.push({
        name: $_("evaluation.main_page.run_model"),
        value: model_name(
          eval_progress.current_run_method.run_config_properties.model_name,
          modelInfo,
        ),
        tooltip: $_("evaluation.main_page.run_model_tooltip"),
      })
      properties.push({
        name: $_("evaluation.main_page.run_prompt"),
        value:
          eval_progress.current_run_method.prompt?.name ||
          prompt_name_from_id(
            eval_progress.current_run_method.run_config_properties.prompt_id,
            taskPrompts,
          ),
        tooltip: $_("evaluation.main_page.run_prompt_tooltip"),
        link: prompt_link(
          project_id,
          task_id,
          eval_progress.current_run_method.run_config_properties.prompt_id,
        ),
      })
    }

    return properties
  }

  $: has_default_eval_config = evaluator && evaluator.current_config_id
  $: has_default_run_config = evaluator && evaluator.current_run_config_id

  let edit_dialog: EditDialog | null = null

  const MIN_DATASET_SIZE = 25
  let current_step: 0 | 1 | 2 | 3 | 4 | 5 | 6 = 0
  let required_more_eval_data = false
  let required_more_golden_data = false
  let goals: string[] = []
  let golden_dataset_explanation = ""
  const step_titles: string[] = [
    $_("evaluation.main_page.step_titles.define_goals"),
    $_("evaluation.main_page.step_titles.create_eval_data"),
    $_("evaluation.main_page.step_titles.human_ratings"),
    $_("evaluation.main_page.step_titles.find_best_evaluator"),
    $_("evaluation.main_page.step_titles.find_best_way"),
  ]
  const step_tooltips: Record<number, string> = {
    1: $_("evaluation.main_page.step_tooltips.define_goals"),
    2: $_("evaluation.main_page.step_tooltips.create_eval_data"),
    3: $_("evaluation.main_page.step_tooltips.human_ratings"),
    4: $_("evaluation.main_page.step_tooltips.find_best_evaluator"),
    5: $_("evaluation.main_page.step_tooltips.find_best_way"),
  }
  function update_eval_progress(
    progress: EvalProgress | null,
    evaluator: Eval | null,
  ) {
    update_golden_dataset_explanation(progress)
    current_step = 1
    if (!progress || !evaluator) {
      return
    }

    // Goals are setup. Generate friendly names for them.
    goals = []
    for (const output of evaluator.output_scores) {
      goals.push(output.name + " (" + output.type + ")")
    }

    current_step = 2
    required_more_eval_data = progress.dataset_size < MIN_DATASET_SIZE
    required_more_golden_data = progress.golden_dataset_size < MIN_DATASET_SIZE
    if (required_more_eval_data || required_more_golden_data) {
      return
    }

    current_step = 3
    if (golden_dataset_explanation) {
      return
    }

    current_step = 4
    if (!has_default_eval_config) {
      return
    }

    current_step = 5
    if (!has_default_run_config) {
      return
    }

    // Everything is setup!
    current_step = 6
  }
  $: update_eval_progress(eval_progress, evaluator)

  function update_golden_dataset_explanation(progress: EvalProgress | null) {
    if (!progress) {
      return
    }
    if (progress.golden_dataset_size == 0) {
      golden_dataset_explanation = $_(
        "evaluation.main_page.golden_dataset_status.empty",
      )
      return
    }
    let golden_dataset_rating_issues: string[] = []
    if (progress.golden_dataset_not_rated_count > 0) {
      const count = progress.golden_dataset_not_rated_count
      const plural = count == 1 ? "" : "s"
      const verb = count == 1 ? "is" : "are"
      golden_dataset_rating_issues.push(
        $_("evaluation.main_page.golden_dataset_status.unrated_items", {
          values: { count, plural, verb },
        }),
      )
    }
    if (progress.golden_dataset_partially_rated_count > 0) {
      const count = progress.golden_dataset_partially_rated_count
      const plural = count == 1 ? "" : "s"
      const verb = count == 1 ? "is" : "are"
      golden_dataset_rating_issues.push(
        $_("evaluation.main_page.golden_dataset_status.partially_rated_items", {
          values: { count, plural, verb },
        }),
      )
    }
    if (golden_dataset_rating_issues.length > 0) {
      // Some golden dataset items are not fully rated.
      const issues = golden_dataset_rating_issues.join($_("common.and"))
      golden_dataset_explanation = $_(
        "evaluation.main_page.golden_dataset_status.unrated",
        {
          values: { issues },
        },
      )
    } else {
      golden_dataset_explanation = ""
    }
  }

  function tag_from_filter_id(filter_id: string): string | undefined {
    if (filter_id.startsWith("tag::")) {
      return filter_id.replace("tag::", "")
    }
    return undefined
  }

  function link_from_filter_id(filter_id: string): string | undefined {
    const tag = tag_from_filter_id(filter_id)
    if (tag) {
      return `/dataset/${project_id}/${task_id}?tags=${tag}`
    }
    return undefined
  }

  $: properties =
    evaluator &&
    get_eval_properties(
      evaluator,
      eval_progress,
      $model_info,
      $current_task_prompts,
    )

  function add_eval_data() {
    if (!evaluator) {
      alert($_("evaluation.main_page.errors.unable_to_add_data"))
      return
    }
    const eval_tag = tag_from_filter_id(evaluator?.eval_set_filter_id)
    const golden_tag = tag_from_filter_id(evaluator?.eval_configs_filter_id)
    if (!eval_tag || !golden_tag) {
      alert($_("evaluation.main_page.errors.no_tag_found"))
      return
    }
    const url = `/dataset/${project_id}/${task_id}/add_data?reason=eval&splits=${encodeURIComponent(
      eval_tag,
    )}:0.8,${encodeURIComponent(golden_tag)}:0.2&eval_link=${encodeURIComponent(
      window.location.pathname,
    )}`
    show_progress_ui(
      $_("evaluation.main_page.creating_eval_progress.when_done_adding"),
      2,
    )
    goto(url)
  }

  function show_progress_ui(body: string, step: number) {
    progress_ui_state.set({
      title: $_("evaluation.main_page.creating_eval_progress.title"),
      body,
      link: $page.url.pathname,
      cta: $_("evaluation.main_page.creating_eval_progress.return_to_eval"),
      progress: null,
      step_count: 5,
      current_step: step,
    })
  }

  function show_golden_dataset() {
    if (!evaluator) {
      return
    }
    const url = link_from_filter_id(evaluator.eval_configs_filter_id)
    if (!url) {
      return
    }

    show_progress_ui(
      $_("evaluation.main_page.creating_eval_progress.when_done_rating"),
      3,
    )
    goto(url)
  }

  function compare_eval_methods() {
    let url = `/evals/${project_id}/${task_id}/${eval_id}/eval_configs`
    show_progress_ui(
      $_(
        "evaluation.main_page.creating_eval_progress.when_done_comparing_eval",
      ),
      4,
    )
    goto(url)
  }

  function compare_run_methods() {
    let url = `/evals/${project_id}/${task_id}/${eval_id}/compare_run_methods`
    show_progress_ui(
      $_("evaluation.main_page.creating_eval_progress.when_done_comparing_run"),
      5,
    )
    goto(url)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("evaluation.main_page.title", {
      values: { name: evaluator?.name || "" },
    })}
    subtitle={$_("evaluation.main_page.subtitle")}
    sub_subtitle={$_("evaluation.main_page.sub_subtitle")}
    sub_subtitle_link="https://docs.getkiln.ai/docs/evaluations"
    action_buttons={[
      {
        label: $_("common.edit"),
        handler: () => {
          edit_dialog?.show()
        },
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          {$_("evaluation.main_page.error_loading")}
        </div>
        <div class="text-error text-sm">
          {error.getMessage() || $_("evaluation.main_page.unknown_error")}
        </div>
      </div>
    {:else if evaluator}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
        <div class="grow">
          <ul class="steps steps-vertical ml-4 overflow-x-hidden">
            {#each [1, 2, 3, 4, 5] as step}
              <li
                class="step {current_step >= step ? 'step-primary' : ''}"
                data-content={current_step == step
                  ? "●"
                  : current_step > step
                    ? "✓"
                    : ""}
              >
                <div
                  class="text-left py-3 min-h-[100px] flex flex-col place-content-center pl-4"
                >
                  <div class="font-medium">
                    {step_titles[step - 1]}
                    {#if step_tooltips[step]}
                      <InfoTooltip
                        tooltip_text={step_tooltips[step]}
                        position={step < 4 ? "bottom" : "top"}
                        no_pad={true}
                      />
                    {/if}
                  </div>
                  <div class="text-sm text-gray-500">
                    {#if step == 1 && goals.length > 0}
                      {$_("evaluation.main_page.goals_description", {
                        values: {
                          count: goals.length,
                          goals: goals.join(", "),
                        },
                      })}
                    {:else if step == 2}
                      <div>
                        <div class="mb-1">
                          {#if eval_progress && !required_more_eval_data && !required_more_golden_data}
                            {$_("evaluation.main_page.data_status.sufficient", {
                              values: {
                                evalSize: eval_progress?.dataset_size,
                                goldenSize: eval_progress?.golden_dataset_size,
                              },
                            })}
                          {:else if eval_progress && eval_progress.dataset_size == 0 && eval_progress.golden_dataset_size == 0}
                            {$_("evaluation.main_page.data_status.empty")}
                          {:else if eval_progress && (required_more_eval_data || required_more_golden_data)}
                            {#if required_more_eval_data && required_more_golden_data}
                              {$_(
                                "evaluation.main_page.data_status.insufficient",
                                {
                                  values: {
                                    evalSize: eval_progress?.dataset_size,
                                    goldenSize:
                                      eval_progress?.golden_dataset_size,
                                    minSize: MIN_DATASET_SIZE,
                                  },
                                },
                              )}
                            {:else if required_more_eval_data}
                              {$_(
                                "evaluation.main_page.data_status.insufficient_eval",
                                {
                                  values: {
                                    evalSize: eval_progress?.dataset_size,
                                    minSize: MIN_DATASET_SIZE,
                                  },
                                },
                              )}
                            {:else if required_more_golden_data}
                              {$_(
                                "evaluation.main_page.data_status.insufficient_golden",
                                {
                                  values: {
                                    goldenSize:
                                      eval_progress?.golden_dataset_size,
                                    minSize: MIN_DATASET_SIZE,
                                  },
                                },
                              )}
                            {/if}
                          {/if}
                        </div>
                        <button
                          class="btn btn-sm {current_step == 2
                            ? 'btn-primary'
                            : ''}"
                          on:click={add_eval_data}
                        >
                          {$_("evaluation.main_page.add_eval_data")}
                        </button>
                      </div>
                    {:else if step == 3}
                      <div class="mb-1">
                        {#if golden_dataset_explanation}
                          {golden_dataset_explanation}
                        {:else}
                          {$_(
                            "evaluation.main_page.golden_dataset_status.complete",
                          )}
                        {/if}
                      </div>
                      <div>
                        {#if link_from_filter_id(evaluator.eval_configs_filter_id)}
                          <button
                            class="btn btn-sm {current_step == 3
                              ? 'btn-primary'
                              : ''}"
                            on:click={show_golden_dataset}
                          >
                            {golden_dataset_explanation
                              ? $_("evaluation.main_page.rate_golden_dataset")
                              : $_("evaluation.main_page.view_golden_dataset")}
                          </button>
                        {:else}
                          <!-- We always use "tag::" so this shouldn't happen unless it's created by code. -->
                          {$_(
                            "evaluation.main_page.golden_dataset_filter_note",
                            {
                              values: {
                                filter: evaluator.eval_configs_filter_id,
                              },
                            },
                          )}
                          <a
                            class="link"
                            href={`/dataset/${project_id}/${task_id}`}
                            >{$_("dataset.title")}</a
                          >.
                        {/if}
                      </div>
                    {:else if step == 4}
                      <div class="mb-1">
                        {#if eval_progress?.current_eval_method}
                          {$_("evaluation.main_page.eval_method_selected", {
                            values: {
                              method: eval_config_to_ui_name(
                                eval_progress.current_eval_method.config_type,
                              ),
                              model: model_name(
                                eval_progress.current_eval_method.model_name,
                                $model_info,
                              ),
                            },
                          })}
                        {:else}
                          {$_("evaluation.main_page.eval_method_not_selected")}
                        {/if}
                      </div>
                      <div>
                        <button
                          class="btn btn-sm {current_step == 4
                            ? 'btn-primary'
                            : ''}"
                          on:click={compare_eval_methods}
                        >
                          {$_("evaluation.main_page.compare_eval_methods")}
                        </button>
                      </div>
                    {:else if step == 5}
                      <div class="mb-1">
                        {#if eval_progress?.current_run_method}
                          {$_("evaluation.main_page.run_method_selected", {
                            values: {
                              model: model_name(
                                eval_progress.current_run_method
                                  .run_config_properties.model_name,
                                $model_info,
                              ),
                              prompt:
                                eval_progress.current_run_method.prompt?.name ||
                                prompt_name_from_id(
                                  eval_progress.current_run_method
                                    .run_config_properties.prompt_id,
                                  $current_task_prompts,
                                ),
                            },
                          })}
                        {:else}
                          {$_("evaluation.main_page.run_method_not_selected")}
                        {/if}
                      </div>
                      <div>
                        <button
                          class="btn btn-sm {current_step == 5
                            ? 'btn-primary'
                            : ''}"
                          on:click={compare_run_methods}
                        >
                          {$_("evaluation.main_page.compare_run_methods")}
                        </button>
                      </div>
                    {/if}
                  </div>
                </div>
              </li>
            {/each}
          </ul>
        </div>

        <div class="w-72 2xl:w-96 flex-none">
          <div class="text-xl font-bold mb-4">
            {$_("evaluation.main_page.evaluator_properties")}
          </div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
          >
            {#each properties || [] as property}
              <div class="flex items-center">
                {property.name}
                {#if property.tooltip}
                  <InfoTooltip tooltip_text={property.tooltip} />
                {/if}
              </div>
              <div class="flex items-center text-gray-500 overflow-x-hidden">
                {#if property.link}
                  <a href={property.link} class="link">{property.value}</a>
                {:else}
                  {property.value}
                {/if}
              </div>
            {/each}
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name={$_("evaluation.main_page.edit_dialog.name")}
  patch_url={`/api/projects/${project_id}/tasks/${task_id}/eval/${eval_id}`}
  delete_url={`/api/projects/${project_id}/tasks/${task_id}/eval/${eval_id}`}
  fields={[
    {
      label: $_("evaluation.main_page.edit_dialog.eval_name_label"),
      description: $_("evaluation.main_page.edit_dialog.eval_name_description"),
      api_name: "name",
      value: evaluator?.name || "",
      input_type: "input",
    },
    {
      label: $_("evaluation.main_page.edit_dialog.description_label"),
      description: $_(
        "evaluation.main_page.edit_dialog.description_description",
      ),
      api_name: "description",
      value: evaluator?.description || "",
      input_type: "textarea",
      optional: true,
    },
  ]}
/>
