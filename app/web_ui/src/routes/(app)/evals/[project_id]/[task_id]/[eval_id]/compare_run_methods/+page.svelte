<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import type { Eval } from "$lib/types"
  import { base_url } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import FormElement from "$lib/utils/form_element.svelte"
  import type {
    EvalConfig,
    TaskRunConfig,
    EvalResultSummary,
    StructuredOutputMode,
    AvailableModels,
  } from "$lib/types"
  import { goto } from "$app/navigation"
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
  import Dialog from "$lib/ui/dialog.svelte"
  import AvailableModelsDropdown from "../../../../../run/available_models_dropdown.svelte"
  import PromptTypeSelector from "../../../../../run/prompt_type_selector.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import RunEval from "../run_eval.svelte"
  import OutputTypeTablePreview from "../output_type_table_preview.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import RunOptions from "$lib/ui/run_options.svelte"
  import { addTaskRunConfig } from "$lib/services/eval-service"
  import type { components } from "$lib/api_schema"
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
  import {
    getEval,
    getEvalConfigs,
    getTaskRunConfigs,
    getScoreSummary,
    setCurrentRunConfig,
    deleteTaskRunConfig,
    getFinetuneBaseModel,
  } from "$lib/services/eval-service"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: eval_id = $page.params.eval_id

  let evaluator: Eval | null = null
  let eval_error: KilnError | null = null
  let eval_loading = true

  let eval_configs: EvalConfig[] | null = null
  let eval_configs_error: KilnError | null = null
  let eval_configs_loading = true
  let current_eval_config_id: string | null = null

  let task_run_configs: TaskRunConfig[] | null = null
  let task_run_configs_error: KilnError | null = null
  let task_run_configs_loading = true

  let score_summary: EvalResultSummary | null = null
  let score_summary_error: KilnError | null = null

  // Store finetune base model information
  let finetune_base_models: Record<string, string> = {}

  // Note: not including score_summary_error, because it's not a critical error we should block the UI for
  $: loading = eval_loading || eval_configs_loading || task_run_configs_loading
  $: error = eval_error || eval_configs_error || task_run_configs_error

  $: should_select_eval_config =
    task_run_configs?.length && !evaluator?.current_run_config_id
  $: focus_select_eval_config = !!(
    should_select_eval_config && eval_state?.includes("complete")
  )

  $: current_eval_config = eval_configs?.find(
    (config) => config.id === current_eval_config_id,
  )

  // Update function calls to use imported helpers:
  $: get_enhanced_model_name = (model_name_param: string | undefined) =>
    getEnhancedModelName(model_name_param, $model_info)
  $: get_enhanced_provider_name = (
    model_name_param: string | undefined,
    provider_name_param: string | undefined,
  ) =>
    getEnhancedProviderName(
      model_name_param,
      provider_name_param,
      finetune_base_models,
    )
  $: get_eval_config_properties = (eval_config_id: string | null) =>
    getEvalConfigProperties(eval_config_id, eval_configs, $model_info)
  $: show_incomplete_warning = (score_summary: EvalResultSummary | null) =>
    showIncompleteWarning(score_summary)

  // Update sortTaskRunConfigs call
  $: sorted_task_run_configs = task_run_configs
    ? sortTaskRunConfigs(
        task_run_configs,
        evaluator,
        score_summary,
        sortState.column,
        sortState.direction,
      )
    : []

  // Update applyFilters call
  $: filtered_task_run_configs = sorted_task_run_configs
    ? applyFilters(sorted_task_run_configs, filter_models, finetune_base_models)
    : []

  // Update is_finetune_model call
  function is_finetune_model(model_name: string | undefined): boolean {
    return isFinetuneModel(model_name)
  }

  // Update get_eval_config_select_options to use the helper
  $: eval_config_select_options = getEvalConfigSelectOptions(
    eval_configs,
    $model_info,
  )

  // Update get_available_filter_models to use the helper
  $: available_filter_models = getAvailableFilterModels(
    sorted_task_run_configs,
    filter_models,
    finetune_base_models,
  )

  // Remove the old function definitions since we're using the helpers now
  // function get_eval_config_select_options(configs: EvalConfig[] | null) { ... }
  // function get_available_filter_models(configs: TaskRunConfig[], currentFilters: string[]) { ... }

  // Keep the component-specific UI handlers
  function toggleSort(column: "created_at" | "score" | "name" | string) {
    if (sortColumn === column) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortColumn = column
      sortDirection = "desc"
    }
  }

  function getSortHeaderClass(): string {
    return "cursor-pointer hover:bg-gray-50"
  }

  onMount(async () => {
    // Wait for page params to load
    await tick()
    // Wait for these 3 to load, as they are needed for better labels. Usually already cached and instant.
    await Promise.all([
      load_model_info(),
      load_available_prompts(),
      load_available_models(),
      load_task(project_id, task_id),
    ])
    // Get the eval first (want it to set the current config id before the other two load)
    await get_eval()
    // These two can be parallel
    await Promise.all([get_eval_configs(), get_task_run_configs()])
    // This needs the selected eval config id, set from above requests
    get_score_summary()
  })

  async function get_eval() {
    try {
      eval_loading = true
      const { data, error } = await getEval(project_id, task_id, eval_id)
      if (error) {
        throw error
      }
      evaluator = data
      // Set the selected eval config: prefer query params, then eval's default, then first eval config (set below in load_eval_configs)
      current_eval_config_id =
        $page.url.searchParams.get("selected_eval_config") ||
        evaluator?.current_config_id ||
        null
    } catch (error) {
      eval_error = createKilnError(error)
    } finally {
      eval_loading = false
    }
  }

  async function get_eval_configs() {
    try {
      eval_configs_loading = true
      const { data, error } = await getEvalConfigs(project_id, task_id, eval_id)
      if (error) {
        throw error
      }
      eval_configs = data
      // Fallback to first eval config if no current eval config id is set from load_eval()
      if (!current_eval_config_id && data && data.length > 0 && data[0]?.id) {
        current_eval_config_id = data[0].id
      }
    } catch (error) {
      eval_configs_error = createKilnError(error)
    } finally {
      eval_configs_loading = false
    }
  }

  async function get_task_run_configs() {
    try {
      task_run_configs_loading = true
      const { data, error } = await getTaskRunConfigs(project_id, task_id)
      if (error) {
        throw error
      }
      task_run_configs = data
      // Load base models immediately after getting task run configs
      if (data) {
        const finetune_models = data
          .map((config) => config.run_config_properties?.model_name)
          .filter((model_name) => model_name && is_finetune_model(model_name))

        // Load base models for all finetune models
        await Promise.all(
          finetune_models.map(async (model_name) => {
            if (model_name) {
              await get_finetune_base_model(model_name)
            }
          }),
        )
        // Force reactivity after all base models are loaded
        finetune_base_models = { ...finetune_base_models }
      }
    } catch (error) {
      task_run_configs_error = createKilnError(error)
    } finally {
      task_run_configs_loading = false
    }
  }

  async function get_score_summary() {
    score_summary = null
    if (!current_eval_config_id) {
      score_summary_error = new KilnError("No evaluation method selected", null)
      return
    }
    try {
      score_summary = null
      const { data, error } = await getScoreSummary(
        project_id,
        task_id,
        eval_id,
        current_eval_config_id,
      )
      if (error) {
        throw error
      }
      score_summary = data
    } catch (error) {
      score_summary_error = createKilnError(error)
    }
  }

  // Watches the current eval config id, performing actions based on it
  $: watch_selected_eval_config(current_eval_config_id)
  function watch_selected_eval_config(selected_id: string | null) {
    if (selected_id === "add_config") {
      // if it's the "add_config" special value, navigate to the create eval config page
      goto(`/evals/${project_id}/${task_id}/${eval_id}/create_eval_config`)
      return
    }
    // If the selected id is not null, then get the score summary
    score_summary = null
    if (selected_id) {
      get_score_summary()
    }
  }

  // Filter state
  let filter_models: string[] = []

  // Sort state
  let sortColumn: "created_at" | "score" | "name" | string | null =
    "Overall Rating"
  let sortDirection: "asc" | "desc" = "desc"

  // Make sort state reactive
  $: sortState = { column: sortColumn, direction: sortDirection }

  let eval_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"
  $: run_eval_url = current_eval_config_id
    ? `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval/${eval_id}/eval_config/${current_eval_config_id}/run_task_run_eval?all_run_configs=true`
    : ""

  let task_run_config_model_name = ""
  let task_run_config_provider_name = ""
  let task_run_config_prompt_method = "simple_prompt_builder"
  let task_run_config_long_prompt_name_provider = ""
  let task_run_config_temperature: number
  let task_run_config_top_p: number
  let task_run_config_structured_output_mode: StructuredOutputMode

  // Update structured_output_mode when model changes
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

  let add_task_config_dialog: Dialog | null = null
  let add_task_config_error: KilnError | null = null
  let delete_dialog: Dialog | null = null
  let delete_run_config_id: string | null = null
  let after_delete: (() => void) | null = null
  let filter_dialog: Dialog | null = null

  async function add_task_config(): Promise<boolean> {
    if (
      !task_run_config_model_name ||
      !task_run_config_provider_name ||
      !task_run_config_prompt_method
    ) {
      add_task_config_error = new KilnError("Missing required fields", null)
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
      if (error) {
        throw error
      }
      // Load the updated list of task run configs after success
      get_task_run_configs()
    } catch (error) {
      add_task_config_error = createKilnError(error)
      return false
    }
    return true
  }

  $: has_default_eval_config = evaluator && evaluator.current_config_id

  async function set_current_run_config(
    run_config_id: string | null | undefined,
  ) {
    if (!run_config_id) {
      return
    }
    try {
      const { data, error } = await setCurrentRunConfig(
        project_id,
        task_id,
        eval_id,
        run_config_id,
      )
      if (error) {
        throw error
      }
      // Update the evaluator with the latest
      evaluator = data
    } catch (error) {
      eval_error = createKilnError(error)
    }
  }

  function show_delete_dialog(run_config_id: string) {
    if (!run_config_id) return
    delete_run_config_id = run_config_id
    after_delete = () => {
      get_task_run_configs()
    }
    delete_dialog?.show()
  }

  async function handleDelete() {
    if (!delete_run_config_id) {
      return false
    }
    try {
      const { success, error } = await deleteTaskRunConfig(
        project_id,
        task_id,
        delete_run_config_id,
      )
      if (error) {
        throw error
      }
      if (success && after_delete) {
        after_delete()
      }
      return success
    } catch (error) {
      eval_error = createKilnError(error)
      return false
    }
  }

  async function get_finetune_base_model(
    model_name: string,
  ): Promise<string | null> {
    if (!is_finetune_model(model_name)) return null

    // Check cache first
    if (finetune_base_models[model_name]) {
      return finetune_base_models[model_name]
    }

    const { baseModelId, error } = await getFinetuneBaseModel(model_name)
    if (error) {
      console.error("Error fetching finetune base model:", error)
      return null
    }

    if (baseModelId) {
      // Cache the result
      finetune_base_models[model_name] = baseModelId
      return baseModelId
    }

    return null
  }

  function add_filter_model(model: string) {
    const newFilters = [...new Set([...filter_models, model])]
    filter_models = newFilters
  }

  function remove_filter_model(model: string) {
    filter_models = filter_models.filter((m) => m !== model)
  }
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
  {:else if evaluator}
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
            bind:value={current_eval_config_id}
            select_options_grouped={eval_config_select_options}
          />
          {#if !has_default_eval_config}
            <Warning
              warning_message="No default evaluation method selected. We recommend using 'Compare Evaluation Methods' and selecting the best performing method as the default."
              warning_color="warning"
              tight={true}
            />
          {:else if has_default_eval_config && evaluator.current_config_id != current_eval_config_id}
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
          {#each get_eval_config_properties(current_eval_config_id) as property}
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
      {#if task_run_configs?.length}
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
              bind:eval_state
              bind:run_url={run_eval_url}
              on_run_complete={() => {
                get_score_summary()
              }}
              button_text="Run All"
            />
          </div>
        </div>

        <!-- Warn the user if some evals are incomplete -->
        {#if show_incomplete_warning(score_summary)}
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
                {#each evaluator.output_scores as output_score}
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
                      `/evals/${project_id}/${task_id}/${eval_id}/${current_eval_config_id}/${task_run_config.id}/run_result`,
                    )
                  }}
                >
                  <td>
                    <div class="font-medium">
                      {get_enhanced_model_name(
                        task_run_config?.run_config_properties?.model_name,
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
                      Provider: {get_enhanced_provider_name(
                        task_run_config?.run_config_properties?.model_name,
                        task_run_config?.run_config_properties
                          ?.model_provider_name,
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
                      {#if task_run_config.id == evaluator.current_run_config_id}
                        <button
                          class="badge badge-primary min-h-[2rem] h-auto px-3 py-1"
                          on:click={(event) => {
                            event.stopPropagation()
                            set_current_run_config("None")
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
                            set_current_run_config(task_run_config.id)
                          }}
                        >
                          Set as default
                        </button>
                      {/if}
                      <RunEval
                        btn_size="sm"
                        run_url={task_run_config.id && current_eval_config_id
                          ? `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval/${eval_id}/eval_config/${current_eval_config_id}/run_task_run_eval?run_config_ids=${encodeURIComponent(task_run_config.id)}&all_run_configs=false`
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
                  {#each evaluator.output_scores as output_score}
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
    {#if add_task_config_error}
      <div class="text-error text-sm">
        {add_task_config_error.getMessage() || "An unknown error occurred"}
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
