<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import type { Eval, Task } from "$lib/types"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import FormElement from "$lib/utils/form_element.svelte"
  import type {
    EvalConfig,
    ProviderModels,
    TaskRunConfig,
    EvalResultSummary,
  } from "$lib/types"
  import { goto } from "$app/navigation"
  import {
    model_info,
    load_model_info,
    model_name,
    provider_name_from_id,
    current_task_prompts,
    load_available_prompts,
    load_available_models,
    load_task,
    get_task_composite_id,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import {
    getDetailedModelName,
    getRunConfigPromptDisplayName,
    getRunConfigPromptInfoText,
  } from "$lib/utils/run_config_formatters"
  import Warning from "$lib/ui/warning.svelte"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import RunEval from "../run_eval.svelte"
  import { eval_config_to_ui_name } from "$lib/utils/formatters"
  import OutputTypeTablePreview from "../output_type_table_preview.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"
  import { prompt_link } from "$lib/utils/link_builder"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { ActionButton } from "../../../../../types"
  import EvalConfigInstruction from "../eval_configs/eval_config_instruction.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: eval_id = $page.params.eval_id

  let task: Task | null = null
  let loading_task = true
  let task_error: KilnError | null = null

  let evaluator: Eval | null = null
  let eval_error: KilnError | null = null
  let eval_loading = true

  let eval_configs: EvalConfig[] | null = null
  let eval_configs_error: KilnError | null = null
  let eval_configs_loading = true
  let current_eval_config_id: string | null = null

  let run_configs_error: KilnError | null = null
  let run_configs_loading = true

  let score_summary: EvalResultSummary | null = null
  let score_summary_error: KilnError | null = null

  // Note: not including score_summary_error, because it's not a critical error we should block the UI for
  $: loading =
    eval_loading || eval_configs_loading || run_configs_loading || loading_task
  $: error = eval_error || eval_configs_error || run_configs_error || task_error

  $: current_task_run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || null

  // Check if all run configs are 100% complete
  $: all_run_configs_complete = score_summary?.run_config_percent_complete
    ? Object.values(score_summary.run_config_percent_complete).every(
        (percent) => percent >= 1.0,
      )
    : false

  $: focus_run_all = !(
    eval_state?.includes("complete") || all_run_configs_complete
  )

  onMount(async () => {
    // Wait for page params to load
    await tick()
    // Wait for these to load, as they are needed for better labels. Usually already cached and instant.
    await Promise.all([
      load_model_info(),
      load_available_prompts(),
      load_available_models(),
      get_task(),
    ])
    // Get the eval first (want it to set the current config id before the other two load)
    await get_eval()
    // These two can be parallel
    await Promise.all([get_eval_configs(), get_task_run_configs()])
    // This needs the selected eval config id, set from above requests
    get_score_summary()
  })

  let create_new_run_config_dialog: CreateNewRunConfigDialog | null = null

  async function get_task() {
    loading_task = true
    try {
      task = await load_task(project_id, task_id)
      if (!task) {
        throw createKilnError("Task not found")
      }
    } catch (err) {
      task_error = createKilnError(err)
    } finally {
      loading_task = false
    }
  }

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
      // Set the selected eval config: prefer query params, then eval's default, then first eval config (set below in load_eval_configs)
      current_eval_config_id =
        $page.url.searchParams.get("selected_eval_config") ||
        evaluator.current_config_id ||
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
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_configs",
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
      eval_configs = data
      // Fallback to first eval config if no current eval config id is set from load_eval()
      if (
        !current_eval_config_id &&
        eval_configs.length > 0 &&
        eval_configs[0].id
      ) {
        current_eval_config_id = eval_configs[0].id
      }
    } catch (error) {
      eval_configs_error = createKilnError(error)
    } finally {
      eval_configs_loading = false
    }
  }

  async function get_task_run_configs() {
    run_configs_loading = true
    try {
      await load_task_run_configs(project_id, task_id)
    } catch (err) {
      run_configs_error = createKilnError(err)
    } finally {
      run_configs_loading = false
    }
  }

  async function get_score_summary() {
    score_summary = null
    if (!current_eval_config_id) {
      score_summary_error = new KilnError("No judge selected", null)
      return
    }
    try {
      score_summary = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/score_summary",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id,
              eval_config_id: current_eval_config_id,
            },
          },
        },
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
    if (selected_id === "__create_new_judge__") {
      // if it's the "create new judge" special value, navigate to the create eval config page
      const params = new URLSearchParams()
      params.set("next_page", "compare_run_configs")
      goto(
        `/evals/${project_id}/${task_id}/${eval_id}/create_eval_config?${params.toString()}`,
      )
      return
    }
    // If the selected id is not null, then get the score summary
    score_summary = null
    if (selected_id) {
      get_score_summary()
    }
  }

  // A dropdown name for the eval config that is human readable and helpful
  // Combine's it's name with it's properties
  function get_eval_config_name(
    eval_config: EvalConfig,
    model_info: ProviderModels | null,
  ): string {
    let parts = []
    parts.push(eval_config_to_ui_name(eval_config.config_type))
    parts.push(
      `${model_name(eval_config.model_name, model_info)} (${provider_name_from_id(eval_config.model_provider)})`,
    )
    return eval_config.name + " — " + parts.join(", ")
  }

  $: current_eval_config = eval_configs?.find(
    (config) => config.id === current_eval_config_id,
  )

  // Sort task run configs - default first, then by last output score
  $: sorted_task_run_configs = current_task_run_configs
    ? sortTaskRunConfigs(current_task_run_configs, evaluator, score_summary)
    : []

  function sortTaskRunConfigs(
    configs: TaskRunConfig[] | null,
    evaluator: Eval | null,
    score_summary: EvalResultSummary | null,
  ): TaskRunConfig[] {
    if (!configs || !configs.length) return []

    return [...configs].sort((a, b) => {
      // Default run config always comes first
      if (a.id === task?.default_run_config_id) return -1
      if (b.id === task?.default_run_config_id) return 1

      // If we have evaluator and score summary, sort by the last output score
      if (evaluator?.output_scores?.length && score_summary?.results) {
        const lastScoreKey = string_to_json_key(
          evaluator.output_scores[evaluator.output_scores.length - 1].name,
        )

        const scoreA =
          score_summary.results["" + a.id]?.[lastScoreKey]?.mean_score
        const scoreB =
          score_summary.results["" + b.id]?.[lastScoreKey]?.mean_score

        // If both have scores, sort by score (higher first)
        if (
          scoreA !== null &&
          scoreA !== undefined &&
          scoreB !== null &&
          scoreB !== undefined
        ) {
          return scoreB - scoreA
        }

        // If only one has a score, it comes first
        if (scoreA !== null && scoreA !== undefined) return -1
        if (scoreB !== null && scoreB !== undefined) return 1
      }

      // Fallback to sort by name
      return a.name.localeCompare(b.name)
    })
  }

  let judge_instructions_dialog: Dialog | null = null

  function get_eval_config_select_options(
    configs: EvalConfig[] | null,
  ): OptionGroup[] {
    let options: OptionGroup[] = []

    options.push({
      label: "",
      options: [
        {
          value: "__create_new_judge__",
          label: "New Judge",
          badge: "＋",
          badge_color: "primary",
        },
      ],
    })

    if (configs && configs.length > 0) {
      options.push({
        label: "Judges",
        options: configs.map((config) => ({
          value: config.id,
          label: get_eval_config_name(config, $model_info),
        })),
      })
    }

    return options
  }

  let eval_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"

  function show_incomplete_warning(
    score_summary: EvalResultSummary | null,
  ): boolean {
    if (!score_summary?.run_config_percent_complete) {
      return false
    }

    const values = Object.values(score_summary.run_config_percent_complete)
    const minComplete =
      values.length > 0
        ? values.reduce((min, val) => Math.min(min, val), 1.0)
        : 1.0
    return minComplete < 1.0
  }

  $: has_default_eval_config = evaluator && evaluator.current_config_id

  function action_buttons(evaluator: Eval | null): ActionButton[] {
    if (evaluator?.template !== "rag") {
      return [
        {
          label: "Compare Judges",
          href: `/evals/${project_id}/${task_id}/${eval_id}/eval_configs`,
          primary: !has_default_eval_config,
        },
      ]
    } else {
      return []
    }
  }
</script>

<AppPage
  title="Compare Run Configurations"
  subtitle="Find the best configuration for running your task."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/evaluations#finding-the-ideal-run-method"
  breadcrumbs={[
    {
      label: "Evals",
      href: `/evals/${$page.params.project_id}/${$page.params.task_id}`,
    },
    {
      label: evaluator?.name || "Eval",
      href: `/evals/${$page.params.project_id}/${$page.params.task_id}/${$page.params.eval_id}`,
    },
  ]}
  action_buttons={action_buttons(evaluator)}
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
          <div class="text-xl font-bold">Judge</div>
          <div class="text-sm text-gray-500 mb-2">
            Select the judge to use when comparing run configurations.
          </div>
          <FormElement
            hide_label={true}
            id="eval_config_select"
            label="Judge"
            inputType="fancy_select"
            bind:value={current_eval_config_id}
            fancy_select_options={get_eval_config_select_options(eval_configs)}
          />
          {#if !has_default_eval_config && evaluator?.template !== "rag"}
            <div class="mt-2">
              <Warning
                warning_message="No default judge selected. We recommend using 'Compare Judges' and selecting the best as the default."
                warning_color="warning"
                tight={true}
              />
            </div>
          {:else if has_default_eval_config && evaluator.current_config_id != current_eval_config_id}
            <div class="mt-2">
              <Warning
                warning_message="The currently selected judge is not the default. You can change the default in 'Compare Judges'."
                warning_color="warning"
                tight={true}
              />
            </div>
          {/if}
        </div>
        {#if current_eval_config_id && evaluator}
          {#if evaluator.template === "rag"}
            <button
              class="flex link text-gray-500 text-sm 2xl:text-base"
              on:click={() => {
                judge_instructions_dialog?.show()
              }}
            >
              Judge Instructions
            </button>
          {:else}
            <div class="flex gap-x-4 text-sm 2xl:text-base items-center">
              <span>Judge Quality</span>
              <a
                href={`/evals/${project_id}/${task_id}/${eval_id}/eval_configs`}
                class="link text-gray-500"
              >
                Compare and optimize
              </a>
            </div>
          {/if}
        {/if}
      </div>
    </div>
    <div class="mt-16">
      {#if current_task_run_configs?.length}
        <div class="flex flex-col lg:flex-row gap-4 lg:gap-8 mb-6">
          <div class="grow">
            <div class="text-xl font-bold">Run Configurations</div>
            <div class="text-xs text-gray-500">
              Find the best method of running your task comparing various
              prompts, models, fine-tunes, and more.
              <InfoTooltip
                tooltip_text={`Scores are generated by running each 'run config' on each item of your eval dataset, generating task outputs. Then those outputs are evaluated with the selected judge (${current_eval_config?.name || "select above"}).`}
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
          </div>
          <div class="shrink-0">
            <button
              class="btn btn-mid mr-2"
              on:click={() => {
                create_new_run_config_dialog?.show()
              }}>Add Run Configuration</button
            >

            <RunEval
              bind:eval_state
              {project_id}
              {task_id}
              {eval_id}
              {current_eval_config_id}
              run_all={true}
              btn_primary={focus_run_all}
              eval_type="run_config"
              on_run_complete={() => {
                get_score_summary()
              }}
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
                warning_message={`Some evals are incomplete and should be excluded from analysis. Click 'Run All Evals' to generate missing results.`}
                tight={true}
              />
            </button>
          </div>
        {/if}

        <div class="overflow-x-auto rounded-lg border">
          <table class="table table-fixed">
            <thead>
              <tr>
                <th class="max-w-[400px]">
                  <div>Run Configuration</div>
                  <div class="font-normal">How task output is generated</div>
                </th>
                <th class="text-center">Status</th>
                {#each evaluator.output_scores as output_score}
                  <th class="text-center">
                    {output_score.name}
                    <OutputTypeTablePreview
                      output_score_type={output_score.type}
                    />
                  </th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each sorted_task_run_configs as task_run_config}
                {@const percent_complete =
                  score_summary?.run_config_percent_complete?.[
                    "" + task_run_config.id
                  ] || 0.0}
                {@const prompt_info_text =
                  getRunConfigPromptInfoText(task_run_config)}
                <tr class="max-w-[400px]">
                  <td>
                    <div class="flex items-center gap-2">
                      <div class="font-medium">
                        {task_run_config.name}
                      </div>
                      {#if task_run_config.id === task?.default_run_config_id}
                        <span
                          class="badge badge-sm badge-primary badge-outline"
                        >
                          Default
                        </span>
                      {/if}
                    </div>
                    <div class="text-sm text-gray-500">
                      Model: {getDetailedModelName(
                        task_run_config,
                        $model_info,
                      )}
                    </div>
                    <div class="text-sm text-gray-500">
                      Prompt: <a
                        href={prompt_link(
                          $page.params.project_id,
                          $page.params.task_id,
                          task_run_config.run_config_properties.prompt_id,
                        )}
                        class="link"
                      >
                        {getRunConfigPromptDisplayName(
                          task_run_config,
                          $current_task_prompts,
                        )}
                      </a>

                      {#if prompt_info_text}
                        <InfoTooltip
                          tooltip_text={prompt_info_text}
                          position="right"
                          no_pad={true}
                        />
                      {/if}
                    </div>
                  </td>
                  <td class="text-sm text-center">
                    {#if percent_complete < 1.0}
                      <div class="text-error">
                        {(percent_complete * 100.0).toFixed(0)}% Complete
                      </div>
                      <div class="mt-1">
                        <RunEval
                          {project_id}
                          {task_id}
                          {eval_id}
                          {current_eval_config_id}
                          run_config_ids={[task_run_config.id || ""]}
                          eval_type="run_config"
                          btn_size="xs"
                          btn_primary={false}
                          btn_class="min-w-[120px]"
                          on_run_complete={() => {
                            get_score_summary()
                          }}
                        />
                      </div>
                    {:else}
                      <div>Complete</div>
                    {/if}
                    {#if percent_complete > 0}
                      <div class="mt-1">
                        <a
                          href={`/evals/${project_id}/${task_id}/${eval_id}/${current_eval_config_id}/${task_run_config.id}/run_result`}
                          class="btn btn-xs btn-outline rounded-full min-w-[120px]"
                        >
                          View Data
                        </a>
                      </div>
                    {/if}
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
        <div class="text-xl font-bold">Compare Run Configurations</div>
        <div class="text-sm text-gray-500">
          Find the best way of running your task comparing various prompts,
          models, tools, fine-tunes, and more. Add one or more task run
          configurations to get started.
        </div>

        <button
          class="btn min-w-[200px] mt-4 {has_default_eval_config
            ? 'btn-primary'
            : ''}"
          on:click={() => {
            create_new_run_config_dialog?.show()
          }}
        >
          Add Run Config
        </button>
      {/if}
    </div>
  {/if}
</AppPage>

<CreateNewRunConfigDialog
  bind:this={create_new_run_config_dialog}
  subtitle="Your evaluator can compare multiple run configurations to find which one produces
    the highest scores on your eval dataset."
  {project_id}
  {task}
/>

<Dialog
  bind:this={judge_instructions_dialog}
  title="Instructions for Judge '{current_eval_config?.name}'"
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  <EvalConfigInstruction bind:eval_config={current_eval_config} />
</Dialog>
