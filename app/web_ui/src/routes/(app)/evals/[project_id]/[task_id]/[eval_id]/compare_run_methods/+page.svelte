<script lang="ts">
  // Core imports
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { base_url } from "$lib/api_client"

  // Types
  import type { Eval } from "$lib/types"
  import type {
    EvalConfig,
    TaskRunConfig,
    EvalResultSummary,
    StructuredOutputMode,
    AvailableModels,
  } from "$lib/types"
  import type { components } from "$lib/api_schema"

  // UI Components
  import AppPage from "../../../../../app_page.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import RunOptions from "$lib/ui/run_options.svelte"
  import AvailableModelsDropdown from "../../../../../run/available_models_dropdown.svelte"
  import PromptTypeSelector from "../../../../../run/prompt_type_selector.svelte"
  import RunEval from "../run_eval.svelte"
  import OutputTypeTablePreview from "../output_type_table_preview.svelte"

  // Utils
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    formatDate,
    isFinetuneModel,
    getEnhancedModelName,
    getEnhancedProviderName,
    getEvalConfigProperties,
    sortTaskRunConfigs,
    applyFilters,
    showIncompleteWarning,
    getEvalConfigSelectOptions,
    getAvailableFilterModels,
  } from "$lib/utils/eval-helpers"

  // Services
  import {
    getEval,
    getEvalConfigs,
    getTaskRunConfigs,
    getScoreSummary,
    setCurrentRunConfig,
    deleteTaskRunConfig,
    getFinetuneBaseModel,
    addTaskRunConfig,
  } from "$lib/services/eval-service"

  // Stores
  import {
    model_info,
    load_model_info,
    model_name,
    prompt_name_from_id,
    current_task_prompts,
    load_available_prompts,
    load_available_models,
    available_model_details,
    available_models,
    current_task,
    load_task,
  } from "$lib/stores"

  // Page params
  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: eval_id = $page.params.eval_id

  // State management
  interface EvalState {
    evaluator: Eval | null
    error: KilnError | null
    loading: boolean
  }

  interface EvalConfigState {
    configs: EvalConfig[] | null
    error: KilnError | null
    loading: boolean
    current_id: string | null
  }

  interface TaskRunConfigState {
    configs: TaskRunConfig[] | null
    error: KilnError | null
    loading: boolean
  }

  const eval_state: EvalState = {
    evaluator: null,
    error: null,
    loading: true,
  }

  const eval_config_state: EvalConfigState = {
    configs: null,
    error: null,
    loading: true,
    current_id: null,
  }

  const task_run_config_state: TaskRunConfigState = {
    configs: null,
    error: null,
    loading: true,
  }

  let score_summary: EvalResultSummary | null = null
  let score_summary_error: KilnError | null = null
  let finetune_base_models: Record<string, string> = {}

  // Computed states
  $: loading =
    eval_state.loading ||
    eval_config_state.loading ||
    task_run_config_state.loading
  $: error =
    eval_state.error || eval_config_state.error || task_run_config_state.error
  $: should_select_eval_config =
    task_run_config_state.configs?.length &&
    !eval_state.evaluator?.current_run_config_id
  $: focus_select_eval_config = !!(
    should_select_eval_config && eval_status?.includes("complete")
  )
  $: current_eval_config = eval_config_state.configs?.find(
    (config) => config.id === eval_config_state.current_id,
  )

  // Sort and filter state
  let filter_models: string[] = []
  let sortColumn: "created_at" | "score" | "name" | string | null =
    "Overall Rating"
  let sortDirection: "asc" | "desc" = "desc"
  $: sortState = { column: sortColumn, direction: sortDirection }

  // Task run config form state
  let task_run_config_model_name = ""
  let task_run_config_provider_name = ""
  let task_run_config_prompt_method = "simple_prompt_builder"
  let task_run_config_long_prompt_name_provider = ""
  let task_run_config_temperature: number
  let task_run_config_top_p: number
  let task_run_config_structured_output_mode: StructuredOutputMode

  // Dialog refs
  let add_task_config_dialog: Dialog | null = null
  let delete_dialog: Dialog | null = null
  let filter_dialog: Dialog | null = null
  let delete_run_config_id: string | null = null
  let after_delete: (() => void) | null = null

  // Eval status
  let eval_status:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"
  $: run_eval_url = eval_config_state.current_id
    ? `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval/${eval_id}/eval_config/${eval_config_state.current_id}/run_task_run_eval?all_run_configs=true`
    : ""

  // Helper functions
  function getSortHeaderClass(): string {
    return "cursor-pointer hover:bg-gray-50"
  }

  function toggleSort(column: "created_at" | "score" | "name" | string) {
    if (sortColumn === column) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortColumn = column
      sortDirection = "desc"
    }
  }

  function add_filter_model(model: string) {
    filter_models = [...new Set([...filter_models, model])]
  }

  function remove_filter_model(model: string) {
    filter_models = filter_models.filter((m) => m !== model)
  }

  function show_delete_dialog(run_config_id: string) {
    if (!run_config_id) return
    delete_run_config_id = run_config_id
    after_delete = () => {
      get_task_run_configs()
    }
    delete_dialog?.show()
  }

  // Data fetching functions
  async function get_eval() {
    try {
      eval_state.loading = true
      const { data, error } = await getEval(project_id, task_id, eval_id)
      if (error) throw error

      eval_state.evaluator = data
      eval_config_state.current_id =
        $page.url.searchParams.get("selected_eval_config") ||
        eval_state.evaluator?.current_config_id ||
        null
    } catch (error) {
      eval_state.error = createKilnError(error)
    } finally {
      eval_state.loading = false
    }
  }

  async function get_eval_configs() {
    try {
      eval_config_state.loading = true
      const { data, error } = await getEvalConfigs(project_id, task_id, eval_id)
      if (error) throw error

      eval_config_state.configs = data
      if (
        !eval_config_state.current_id &&
        data &&
        data.length > 0 &&
        data[0]?.id
      ) {
        eval_config_state.current_id = data[0].id || null
      }
    } catch (error) {
      eval_config_state.error = createKilnError(error)
    } finally {
      eval_config_state.loading = false
    }
  }

  async function get_task_run_configs() {
    try {
      task_run_config_state.loading = true
      const { data, error } = await getTaskRunConfigs(project_id, task_id)
      if (error) throw error

      task_run_config_state.configs = data
      if (data) {
        const finetune_models = data
          .map((config) => config.run_config_properties?.model_name)
          .filter((model_name) => model_name && isFinetuneModel(model_name))

        await Promise.all(
          finetune_models.map(async (model_name) => {
            if (model_name) {
              await get_finetune_base_model(model_name)
            }
          }),
        )
        finetune_base_models = { ...finetune_base_models }
      }
    } catch (error) {
      task_run_config_state.error = createKilnError(error)
    } finally {
      task_run_config_state.loading = false
    }
  }

  async function get_score_summary() {
    score_summary = null
    if (!eval_config_state.current_id) {
      score_summary_error = new KilnError("No evaluation method selected", null)
      return
    }

    try {
      const { data, error } = await getScoreSummary(
        project_id,
        task_id,
        eval_id,
        eval_config_state.current_id,
      )
      if (error) throw error
      score_summary = data
    } catch (error) {
      score_summary_error = createKilnError(error)
    }
  }

  async function get_finetune_base_model(
    model_name: string,
  ): Promise<string | null> {
    if (!isFinetuneModel(model_name)) return null
    if (finetune_base_models[model_name])
      return finetune_base_models[model_name]

    const { baseModelId, error } = await getFinetuneBaseModel(model_name)
    if (error) {
      console.error("Error fetching finetune base model:", error)
      return null
    }

    if (baseModelId) {
      finetune_base_models[model_name] = baseModelId
      return baseModelId
    }

    return null
  }

  async function handleDelete(): Promise<boolean> {
    if (!delete_run_config_id) return false

    try {
      const { success, error } = await deleteTaskRunConfig(
        project_id,
        task_id,
        delete_run_config_id,
      )
      if (error) throw error

      if (success && after_delete) {
        after_delete()
      }
      return success
    } catch (error) {
      eval_state.error = createKilnError(error)
      return false
    }
  }

  async function add_task_config(): Promise<boolean> {
    if (
      !task_run_config_model_name ||
      !task_run_config_provider_name ||
      !task_run_config_prompt_method
    ) {
      return false
    }

    try {
      const { error } = await addTaskRunConfig(project_id, task_id, {
        model_name: task_run_config_model_name,
        model_provider_name:
          task_run_config_provider_name as components["schemas"]["ModelProviderName"],
        prompt_id: task_run_config_prompt_method,
        temperature: task_run_config_temperature,
        top_p: task_run_config_top_p,
        structured_output_mode: task_run_config_structured_output_mode,
      })
      if (error) throw error

      get_task_run_configs()
      return true
    } catch (error) {
      eval_state.error = createKilnError(error)
      return false
    }
  }

  // Lifecycle
  onMount(async () => {
    await tick()
    await Promise.all([
      load_model_info(),
      load_available_prompts(),
      load_available_models(),
      load_task(project_id, task_id),
    ])
    await get_eval()
    await Promise.all([get_eval_configs(), get_task_run_configs()])
    get_score_summary()
  })

  // Watchers
  $: watch_selected_eval_config(eval_config_state.current_id)
  function watch_selected_eval_config(selected_id: string | null) {
    if (selected_id === "add_config") {
      goto(`/evals/${project_id}/${task_id}/${eval_id}/create_eval_config`)
      return
    }
    score_summary = null
    if (selected_id) {
      get_score_summary()
    }
  }

  // Update structured output mode when model changes
  $: update_structured_output_mode(
    task_run_config_model_name,
    task_run_config_provider_name,
    $available_models,
  )
  function update_structured_output_mode(
    model_name: string,
    provider: string,
    available_models: AvailableModels[],
  ) {
    task_run_config_structured_output_mode =
      available_model_details(model_name, provider, available_models)
        ?.structured_output_mode || "default"
  }

  // Computed values for UI
  $: sorted_task_run_configs = task_run_config_state.configs
    ? sortTaskRunConfigs(
        task_run_config_state.configs,
        eval_state.evaluator,
        score_summary,
        sortState.column,
        sortState.direction,
      )
    : []

  $: filtered_task_run_configs = sorted_task_run_configs
    ? applyFilters(sorted_task_run_configs, filter_models, finetune_base_models)
    : []

  $: eval_config_select_options = getEvalConfigSelectOptions(
    eval_config_state.configs,
    $model_info,
  )

  $: available_filter_models = getAvailableFilterModels(
    sorted_task_run_configs,
    filter_models,
    finetune_base_models,
  )

  $: has_default_eval_config =
    eval_state.evaluator && eval_state.evaluator.current_config_id
</script>

<AppPage
  title="Compare Run Methods"
  subtitle="Find the best method of running your task."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.getkiln.ai/docs/evaluations#finding-the-ideal-run-method"
  action_buttons={[
    {
      label: "Compare Evaluation Methods",
      href: `/evals/${project_id}/${task_id}/${eval_id}/eval_configs`,
      primary: !has_default_eval_config,
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
      <div class="font-medium">Error Loading Evaluator</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if eval_state.evaluator}
    <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
      <div class="grow flex flex-col gap-4">
        <div>
          <div class="text-xl font-bold">Evaluation Method</div>
          <div class="text-sm text-gray-500 mb-2">
            How the task outputs will be evaluated for the comparison.
          </div>

          <FormElement
            hide_label={true}
            id="eval_config_select"
            label="Eval Method"
            inputType="select"
            bind:value={eval_config_state.current_id}
            select_options_grouped={eval_config_select_options}
          />
          {#if !has_default_eval_config}
            <Warning
              warning_message="No default evaluation method selected. We recommend using 'Compare Evaluation Methods' and selecting the best performing method as the default."
              warning_color="warning"
              tight={true}
            />
          {:else if has_default_eval_config && eval_state.evaluator.current_config_id != eval_config_state.current_id}
            <Warning
              warning_message="The currently selected evaluation method is not the default. You can change the default in 'Compare Evaluation Methods'."
              warning_color="warning"
              tight={true}
            />
          {/if}
        </div>
        <div
          class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
        >
          {#each getEvalConfigProperties(eval_config_state.current_id, eval_config_state.configs, $model_info) as property}
            <div class="flex items-center">{property.name}</div>
            <div class="flex items-center text-gray-500 overflow-x-hidden">
              {property.value}
            </div>
          {/each}
          <div class="flex items-center">Eval Method Quality</div>
          <div class="flex items-center text-gray-500 overflow-x-hidden">
            <a
              href={`/evals/${project_id}/${task_id}/${eval_id}/eval_configs`}
              class="link"
            >
              Compare and optimize
            </a>
          </div>
        </div>
      </div>
    </div>
    <div class="mt-16">
      {#if task_run_config_state.configs?.length}
        <div class="flex flex-col lg:flex-row gap-4 lg:gap-8 mb-6">
          <div class="grow">
            <div class="text-xl font-bold">Run Methods</div>
            <div class="text-xs text-gray-500">
              Find the best method of running your task comparing various
              prompts, models, fine-tunes, and more.
              <InfoTooltip
                tooltip_text={`Scores are generated by running each 'run method' on each item of your eval dataset, generating task outputs. Then those outputs are evaluated with the selected evaluation method (${current_eval_config?.name || "select above"}).`}
                position="left"
                no_pad={true}
              />
            </div>
            {#if score_summary_error}
              <div class="text-error text-sm">
                {score_summary_error.getMessage() ||
                  "An unknown error occurred fetching scores."}
              </div>
            {/if}
            {#if filter_models.length > 0}
              <div class="text-xs text-gray-500 mt-1">
                Showing {filtered_task_run_configs.length} of {sorted_task_run_configs.length}
                run methods
              </div>
            {/if}
          </div>
          <div class="shrink-0">
            <button
              class="btn btn-mid mr-2"
              on:click={() => {
                add_task_config_dialog?.show()
              }}>Add Run Method</button
            >
            <button
              class="btn btn-mid mr-2 !px-3"
              on:click={() => filter_dialog?.show()}
            >
              <img alt="filter" src="/images/filter.svg" class="w-5 h-5" />
              {#if filter_models.length > 0}
                <span class="badge badge-primary badge-sm"
                  >{filter_models.length}</span
                >
              {/if}
            </button>
            <RunEval
              bind:eval_state={eval_status}
              bind:run_url={run_eval_url}
              on_run_complete={() => {
                get_score_summary()
              }}
              button_text="Run"
            />
          </div>
        </div>

        <!-- Warn the user if some evals are incomplete -->
        {#if showIncompleteWarning(score_summary)}
          <div class="mt-6 mb-4">
            <button
              class="tooltip tooltip-top cursor-pointer"
              data-tip="Running evals will update any missing dataset items, without re-running complete items. If some evals consistently fail, check the logs for error details."
            >
              <Warning
                warning_message={`Some evals are incomplete and should be excluded from analysis. Click 'Run Eval' to generate missing results.`}
                tight={true}
              />
            </button>
          </div>
        {:else if should_select_eval_config}
          <div class="mb-4">
            <Warning
              warning_message="Click 'Set as default' below to select a winner."
              warning_color={focus_select_eval_config ? "primary" : "gray"}
              warning_icon="info"
              large_icon={focus_select_eval_config}
              tight={true}
            />
          </div>
        {/if}

        <div class="overflow-x-auto rounded-lg border">
          <table class="table">
            <thead>
              <tr>
                <th
                  class={getSortHeaderClass()}
                  on:click={(e) => {
                    e.stopPropagation()
                    toggleSort("name")
                  }}
                >
                  <div class="flex items-center gap-1">Run Method</div>
                  <div class="font-normal">How task output is generated</div>
                </th>
                <th
                  class={`${getSortHeaderClass()} text-center`}
                  on:click={(e) => {
                    e.stopPropagation()
                    toggleSort("created_at")
                  }}
                >
                  <div class="flex items-center justify-center gap-1">
                    Date Created
                  </div>
                </th>
                {#each eval_state.evaluator.output_scores as output_score}
                  <th
                    class={`text-center ${getSortHeaderClass()}`}
                    on:click={(e) => {
                      e.stopPropagation()
                      toggleSort(output_score.name)
                    }}
                  >
                    <div class="flex items-center justify-center gap-1">
                      {output_score.name}
                    </div>
                    <OutputTypeTablePreview
                      output_score_type={output_score.type}
                    />
                  </th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each filtered_task_run_configs as task_run_config}
                {@const percent_complete =
                  score_summary?.run_config_percent_complete?.[
                    "" + task_run_config.id
                  ]}
                <tr
                  class="hover cursor-pointer"
                  on:click={() => {
                    goto(
                      `/evals/${project_id}/${task_id}/${eval_id}/${eval_config_state.current_id}/${task_run_config.id}/run_result`,
                    )
                  }}
                >
                  <td>
                    <div class="font-medium">
                      {getEnhancedModelName(
                        task_run_config?.run_config_properties?.model_name,
                        $model_info,
                      )}
                    </div>

                    <div class="text-sm text-gray-500">
                      Prompt:
                      {#if task_run_config?.prompt?.generator_id && task_run_config?.run_config_properties?.prompt_id?.startsWith("task_run_config::")}
                        <!-- Special description for prompts frozen to the task run config. The name alone isn't that helpful, so we say where it comes from (eg "Basic (Zero Shot")) -->
                        {prompt_name_from_id(
                          task_run_config?.prompt?.generator_id,
                          $current_task_prompts,
                        )}
                        <InfoTooltip
                          tooltip_text={'The exact prompt was saved under the name "' +
                            prompt_name_from_id(
                              task_run_config?.prompt?.generator_id,
                              $current_task_prompts,
                            ) +
                            '". See the Prompt tab for details.'}
                          position="right"
                          no_pad={true}
                        />
                      {:else}
                        {prompt_name_from_id(
                          task_run_config?.run_config_properties?.prompt_id,
                          $current_task_prompts,
                        )}
                      {/if}
                    </div>
                    <div class="text-sm text-gray-500">
                      Provider: {getEnhancedProviderName(
                        task_run_config?.run_config_properties?.model_name,
                        task_run_config?.run_config_properties
                          ?.model_provider_name,
                        finetune_base_models,
                      )}
                    </div>
                    <div class="text-sm text-gray-500">
                      Run Method Name: {task_run_config.name}
                    </div>
                    {#if percent_complete}
                      {#if percent_complete < 1.0}
                        <div class="text-sm text-error">
                          Progress: {(percent_complete * 100).toFixed(2)}%
                        </div>
                      {/if}
                    {:else if score_summary}
                      <div class="text-sm text-error">Progress: 0%</div>
                    {/if}
                    <div class="flex flex-row gap-2 mt-2 items-center">
                      {#if task_run_config.id == eval_state.evaluator.current_run_config_id}
                        <button
                          class="badge badge-primary min-h-[2rem] h-auto px-3 py-1"
                          on:click={(event) => {
                            event.stopPropagation()
                            setCurrentRunConfig(
                              project_id,
                              task_id,
                              eval_id,
                              "None",
                            )
                          }}
                        >
                          Default <span class="pl-2">&#x2715;</span>
                        </button>
                      {:else}
                        <button
                          class="badge {focus_select_eval_config
                            ? 'badge-primary'
                            : 'badge-secondary badge-outline'} min-h-[2rem] h-auto px-3 py-1"
                          on:click={(event) => {
                            event.stopPropagation()
                            if (task_run_config.id) {
                              setCurrentRunConfig(
                                project_id,
                                task_id,
                                eval_id,
                                task_run_config.id,
                              )
                            }
                          }}
                        >
                          Set as default
                        </button>
                      {/if}
                      <RunEval
                        btn_size="sm"
                        run_url={task_run_config.id &&
                        eval_config_state.current_id
                          ? `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval/${eval_id}/eval_config/${eval_config_state.current_id}/run_task_run_eval?run_config_ids=${encodeURIComponent(task_run_config.id)}&all_run_configs=false`
                          : ""}
                        on_run_complete={() => {
                          get_score_summary()
                        }}
                        button_text="Run"
                      />
                      <button
                        class="btn btn-sm btn-error min-h-[2rem]"
                        on:click={(event) => {
                          event.stopPropagation()
                          if (task_run_config.id) {
                            show_delete_dialog(task_run_config.id)
                          }
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                  <td class="text-center whitespace-pre-line">
                    <div class="flex flex-col items-center">
                      {formatDate(task_run_config.created_at)}
                    </div>
                  </td>
                  {#each eval_state.evaluator.output_scores as output_score}
                    {@const score =
                      score_summary?.results?.["" + task_run_config.id]?.[
                        string_to_json_key(output_score.name)
                      ]?.mean_score}
                    <td class="text-center">
                      {score != null ? score.toFixed(2) : "unknown"}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="text-xl font-bold">Compare Run Methods</div>
        <div class="text-sm text-gray-500">
          Find the best method of running your task comparing various prompts,
          models, fine-tunes, and more. Add one or more task run methods to get
          started.
        </div>

        <button
          class="btn min-w-[200px] mt-4 {has_default_eval_config
            ? 'btn-primary'
            : ''}"
          on:click={() => {
            add_task_config_dialog?.show()
          }}
        >
          Add Run Method
        </button>
      {/if}
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={add_task_config_dialog}
  title="Add a Task Run Method"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Create",
      isPrimary: true,
      asyncAction: add_task_config,
    },
  ]}
>
  <h4 class="text-sm text-gray-500">
    Define a method of running this task (model+prompt).
  </h4>
  <h4 class="text-sm text-gray-500 mt-1">
    Your evaluator can compare multiple run methods to find which one produces
    the highest scores on your eval dataset.
  </h4>
  <div class="flex flex-col gap-2 pt-6">
    <AvailableModelsDropdown
      bind:model_name={task_run_config_model_name}
      bind:provider_name={task_run_config_provider_name}
      bind:model={task_run_config_long_prompt_name_provider}
    />
    <PromptTypeSelector
      bind:prompt_method={task_run_config_prompt_method}
      bind:linked_model_selection={task_run_config_long_prompt_name_provider}
    />
    <Collapse title="Advanced Options">
      <RunOptions
        bind:temperature={task_run_config_temperature}
        bind:top_p={task_run_config_top_p}
        bind:structured_output_mode={task_run_config_structured_output_mode}
        has_structured_output={!!$current_task?.output_json_schema}
      />
    </Collapse>
    {#if eval_state.error}
      <div class="text-error text-sm">
        {eval_state.error.getMessage() || "An unknown error occurred"}
      </div>
    {/if}
  </div>
</Dialog>

<Dialog
  bind:this={delete_dialog}
  title="Delete Run Method"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Delete",
      isPrimary: true,
      asyncAction: handleDelete,
    },
  ]}
>
  <div class="text-sm text-gray-500">
    Are you sure you want to delete this run method? This action cannot be
    undone.
  </div>
</Dialog>

<Dialog
  bind:this={filter_dialog}
  title="Filter Run Methods by Base Model"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  <div class="space-y-4">
    {#if filter_models.length > 0}
      <div>
        <div class="text-sm mb-2 font-medium">Current Filters:</div>
        <div class="flex flex-row gap-2 flex-wrap mb-6">
          {#each filter_models as model}
            <div
              class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full whitespace-normal text-left min-h-[2.5rem] h-auto leading-tight"
            >
              <span class="truncate break-words"
                >{model_name(model, $model_info)}</span
              >
              <button
                class="pl-3 font-medium shrink-0"
                on:click={() => remove_filter_model(model)}>✕</button
              >
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <div>
      <div class="text-sm mt-4 mb-4 font-medium">Add a filter:</div>

      <!-- Base Models Section -->
      {#if Object.keys(available_filter_models.base_models).length > 0}
        <div class="mb-6">
          <div class="text-sm mb-2 font-semibold text-gray-700">
            Base Models:
          </div>
          <div class="flex flex-row gap-2 flex-wrap">
            {#each Object.entries(available_filter_models.base_models).sort((a, b) => b[1] - a[1]) as [model, count]}
              <button
                class="badge bg-blue-100 text-blue-700 py-3 px-3 max-w-full hover:bg-blue-200 whitespace-normal text-left min-h-[2.5rem] h-auto leading-tight"
                on:click={() => add_filter_model(model)}
                ><span class="break-words"
                  >{model_name(model, $model_info)} ({count})</span
                ></button
              >
            {/each}
          </div>
        </div>
      {/if}

      <!-- Fine-tuned Models Section -->
      {#if Object.keys(available_filter_models.finetune_base_models).length > 0}
        <div class="mb-6">
          <div class="text-sm mb-2 font-semibold text-gray-700">
            Fine-tuned Models (by base model):
          </div>
          <div class="flex flex-row gap-2 flex-wrap">
            {#each Object.entries(available_filter_models.finetune_base_models).sort((a, b) => b[1] - a[1]) as [base_model, count]}
              <button
                class="badge bg-green-100 text-green-700 py-3 px-3 max-w-full hover:bg-green-200 whitespace-normal text-left min-h-[2.5rem] h-auto leading-tight"
                on:click={() => add_filter_model(base_model)}
                ><span class="break-words">{base_model} ({count})</span></button
              >
            {/each}
          </div>
        </div>
      {/if}

      {#if Object.keys(available_filter_models.base_models).length === 0 && Object.keys(available_filter_models.finetune_base_models).length === 0}
        <p class="text-sm text-gray-500 mt-4">
          Any further filters would show zero results.
        </p>
      {/if}
    </div>
  </div>
</Dialog>
