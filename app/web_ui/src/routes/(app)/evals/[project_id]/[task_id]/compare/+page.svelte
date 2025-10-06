<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { onMount, tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { Task, TaskRunConfig } from "$lib/types"
  import type { components } from "$lib/api_schema"
  import RunEval from "../[eval_id]/run_eval.svelte"

  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]
  type ScoreSummary = components["schemas"]["ScoreSummary"]
  import {
    model_info,
    load_model_info,
    current_task_prompts,
    load_available_prompts,
    load_available_models,
    get_task_composite_id,
    load_task,
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
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import { prompt_link } from "$lib/utils/link_builder"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let task: Task | null = null

  // State management
  let columns = 2 // Start with 2 columns
  let selectedModels: (string | null)[] = [null, null] // Track selected model for each column

  // Run configs state
  let loading = true
  let error: KilnError | null = null

  // Eval scores cache and state
  let eval_scores_cache: Record<string, RunConfigEvalScoresSummary> = {}
  let eval_scores_loading: Record<string, boolean> = {}
  let eval_scores_errors: Record<string, string> = {}

  // Track if we're initializing from URL to avoid updating URL during initial load
  let isInitializing = true

  // Initialize basic state from URL parameters (columns only)
  function initializeFromURL() {
    const urlParams = new URLSearchParams($page.url.search)

    // Get columns from URL
    const urlColumns = urlParams.get("columns")
    if (urlColumns) {
      const parsedColumns = parseInt(urlColumns, 10)
      if (parsedColumns >= 2 && parsedColumns <= 4) {
        columns = parsedColumns
      }
    }

    // Initialize selectedModels array with correct length
    selectedModels = new Array(columns).fill(null)
  }

  // Restore model selections from URL after data is loaded
  function restoreStateFromURL() {
    if (!current_task_run_configs) return

    const urlParams = new URLSearchParams($page.url.search)
    const urlModels = urlParams.get("models")

    if (urlModels) {
      const modelIds = urlModels.split(",").map((id) => (id === "" ? null : id))

      // Validate each model ID exists in task_run_configs
      for (let i = 0; i < Math.min(modelIds.length, columns); i++) {
        const modelId = modelIds[i]
        if (
          modelId &&
          current_task_run_configs.find((config) => config.id === modelId)
        ) {
          selectedModels[i] = modelId
        }
      }

      // Trigger reactivity
      selectedModels = [...selectedModels]
    }
  }

  // Update URL with current state
  function updateURL() {
    if (isInitializing) return

    const urlParams = new URLSearchParams($page.url.search)

    // Update columns
    urlParams.set("columns", columns.toString())

    // Update models (empty string for null values)
    const modelIds = selectedModels.map((id) => id || "")
    urlParams.set("models", modelIds.join(","))

    // Use replace to avoid creating new history entries
    const newURL = `${$page.url.pathname}?${urlParams.toString()}`
    goto(newURL, { replaceState: true })
  }

  // Reactive statements to update URL when state changes
  $: if (!isInitializing && (columns || selectedModels)) {
    updateURL()
  }

  onMount(async () => {
    // Wait for page params to load
    await tick()

    // Initialize basic state from URL first (columns)
    initializeFromURL()

    // Load data needed for the page
    await Promise.all([
      load_model_info(),
      load_available_prompts(),
      load_available_models(),
    ])
    await get_task_run_configs()
    task = await load_task(project_id, task_id)
    if (!task) {
      error = createKilnError("Task not found")
    }

    // Now that data is loaded, restore full state from URL
    restoreStateFromURL()

    // Mark initialization as complete
    isInitializing = false
  })

  async function get_task_run_configs() {
    loading = true
    try {
      await load_task_run_configs(project_id, task_id)
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  async function fetch_eval_scores(run_config_id: string) {
    if (
      eval_scores_cache[run_config_id] ||
      eval_scores_loading[run_config_id]
    ) {
      return // Already cached or loading
    }

    try {
      eval_scores_loading[run_config_id] = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/run_config/{run_config_id}/eval_scores",
        {
          params: {
            path: {
              project_id,
              task_id,
              run_config_id,
            },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      eval_scores_cache[run_config_id] = data
      delete eval_scores_errors[run_config_id]
    } catch (err) {
      const kilnError = createKilnError(err)
      eval_scores_errors[run_config_id] =
        kilnError.getMessage() || "Failed to fetch eval scores"
    } finally {
      eval_scores_loading[run_config_id] = false
    }
  }

  // Reactively fetch eval scores when models are selected
  $: {
    selectedModels.forEach((modelId) => {
      if (
        modelId &&
        modelId !== "__create_new_run_config__" &&
        !eval_scores_cache[modelId] &&
        !eval_scores_loading[modelId]
      ) {
        fetch_eval_scores(modelId)
      }
    })
  }

  // Generate comparison features dynamically from eval_scores
  $: comparisonFeatures = generateComparisonFeatures(
    selectedModels,
    eval_scores_cache,
  )

  function generateComparisonFeatures(
    models: (string | null)[],
    scores_cache: Record<string, RunConfigEvalScoresSummary>,
  ) {
    const features: {
      category: string
      items: { label: string; key: string }[]
      has_default_eval_config: boolean | undefined
      eval_id: string
    }[] = []
    const evalCategories: Record<string, Set<string>> = {}
    const hasDefaultEvalConfig: Record<string, boolean> = {}
    const evalIds: Record<string, string> = {}

    // Collect all evals and their scores from selected models
    models.forEach((modelId) => {
      if (!modelId || !scores_cache[modelId]) return

      const evalScores = scores_cache[modelId]
      evalScores.eval_results.forEach((evalResult) => {
        hasDefaultEvalConfig[evalResult.eval_name] =
          !evalResult.missing_default_eval_config
        evalIds[evalResult.eval_name] = evalResult.eval_id || ""

        if (!evalCategories[evalResult.eval_name]) {
          evalCategories[evalResult.eval_name] = new Set()
        }

        Object.keys(evalResult.eval_config_result?.results || {}).forEach(
          (scoreKey) => {
            evalCategories[evalResult.eval_name].add(scoreKey)
          },
        )
      })
    })

    // Convert to comparison features format
    Object.entries(evalCategories).forEach(([evalName, scoreKeys]) => {
      const items = Array.from(scoreKeys).map((scoreKey) => ({
        label: scoreKey
          .replace(/_/g, " ")
          .replace(/\b\w/g, (l) => l.toUpperCase()),
        key: `${evalName}::${scoreKey}`,
      }))

      features.push({
        category: evalName,
        items,
        has_default_eval_config: hasDefaultEvalConfig[evalName],
        eval_id: evalIds[evalName],
      })
    })

    // Add Cost section (always last)
    const costItems = [
      { label: "Input Tokens", key: "cost::mean_input_tokens" },
      { label: "Output Tokens", key: "cost::mean_output_tokens" },
      { label: "Total Tokens", key: "cost::mean_total_tokens" },
      { label: "Cost (USD)", key: "cost::mean_cost" },
    ]

    features.push({
      category: "Average Usage & Cost",
      items: costItems,
      has_default_eval_config: undefined,
      eval_id: "kiln_cost_section",
    })

    return features
  }

  // Generate dropdown options from run configs
  $: current_task_run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || null

  let target_new_run_config_col: number | null = null
  let create_new_run_config_dialog: CreateNewRunConfigDialog | null = null
  $: if (selectedModels.includes("__create_new_run_config__")) {
    target_new_run_config_col = selectedModels.indexOf(
      "__create_new_run_config__",
    )
    create_new_run_config_dialog?.show()
  }

  function addColumn() {
    if (columns < 4) {
      columns++
      selectedModels = [...selectedModels, null]
    }
  }

  function removeColumn(index: number) {
    if (columns > 2) {
      columns--
      selectedModels = selectedModels.filter((_, i) => i !== index)
    }
  }

  function getModelValue(modelKey: string | null, dataKey: string): string {
    if (!modelKey || !eval_scores_cache[modelKey]) return "—"

    const [category, scoreKey] = dataKey.split("::")
    if (!category || !scoreKey) return "—"

    const evalScores = eval_scores_cache[modelKey]

    // Handle cost metrics
    if (category === "cost") {
      if (!evalScores.mean_usage) return "—"

      const meanUsage = evalScores.mean_usage
      let value: number | null | undefined = null

      switch (scoreKey) {
        case "mean_input_tokens":
          value = meanUsage.mean_input_tokens
          break
        case "mean_output_tokens":
          value = meanUsage.mean_output_tokens
          break
        case "mean_total_tokens":
          value = meanUsage.mean_total_tokens
          break
        case "mean_cost":
          value = meanUsage.mean_cost
          break
      }

      if (value !== null && value !== undefined) {
        // Format cost with currency symbol, others as whole numbers
        if (scoreKey === "mean_cost") {
          return `$${value.toFixed(7)}`
        } else {
          return value.toFixed(1)
        }
      }

      return "—"
    }

    // Handle eval metrics (existing logic)
    const evalResult = evalScores.eval_results.find(
      (e) => e.eval_name === category,
    )
    if (!evalResult) return "—"

    const score: ScoreSummary | null | undefined =
      evalResult.eval_config_result?.results[scoreKey]
    if (score) {
      return score.mean_score.toFixed(2)
    }

    return "—"
  }

  function getModelPercentComplete(
    modelKey: string | null,
    evalID: string | null,
  ): number {
    if (evalID === "kiln_cost_section") return 1.0
    if (!modelKey || !eval_scores_cache[modelKey]) return 0.0

    const evalScores = eval_scores_cache[modelKey]
    const evalResult = evalScores.eval_results.find((e) => e.eval_id === evalID)

    if (!evalResult) return 0.0

    return evalResult.eval_config_result?.percent_complete || 0.0
  }

  function getModelDefaultEvalConfigID(
    modelKey: string | null,
    evalID: string | null,
  ): string | null | undefined {
    if (evalID === "kiln_cost_section") return null
    if (!modelKey || !eval_scores_cache[modelKey]) return null

    const evalScores = eval_scores_cache[modelKey]
    const evalResult = evalScores.eval_results.find((e) => e.eval_id === evalID)

    if (!evalResult) return null

    return evalResult.eval_config_result?.eval_config_id
  }

  function getSelectedRunConfig(modelKey: string | null): TaskRunConfig | null {
    if (!modelKey || !current_task_run_configs) return null
    return (
      current_task_run_configs.find((config) => config.id === modelKey) || null
    )
  }

  function getPercentageDifference(
    baseValue: string,
    compareValue: string,
  ): string {
    // Return empty if either value is unavailable
    if (baseValue === "—" || compareValue === "—") return ""

    // Parse numeric values, handling currency formatting
    const parseValue = (val: string): number | null => {
      if (val === "—") return null
      // Remove currency symbol and parse
      const cleaned = val.replace(/^\$/, "")
      const parsed = parseFloat(cleaned)
      return isNaN(parsed) ? null : parsed
    }

    const base = parseValue(baseValue)
    const compare = parseValue(compareValue)

    if (base === null || compare === null) return ""

    // Handle division by zero
    if (base === 0) {
      if (compare === 0) return "even"
      return "N/A"
    }

    const percentDiff = ((compare - base) / base) * 100

    // Handle very small differences (less than 0.01%)
    if (Math.abs(percentDiff) < 0.01) return "even"

    // Format the percentage
    const formatted =
      Math.abs(percentDiff) < 1
        ? percentDiff.toFixed(2)
        : Math.abs(percentDiff) < 10
          ? percentDiff.toFixed(1)
          : percentDiff.toFixed(0)

    return percentDiff >= 0 ? `+${formatted}%` : `${formatted}%`
  }

  function getValidSelectedModels(): string[] {
    return selectedModels.filter(
      (m): m is string => m !== null && m !== "__create_new_run_config__",
    )
  }
</script>

<AppPage
  title="Compare Run Configurations"
  subtitle="Compare run Configurations for your task using evals"
  breadcrumbs={[{ label: "Evals", href: `/evals/${project_id}/${task_id}` }]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Run Configurations</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else}
    {@const hasSelectedModels = getValidSelectedModels()}
    {@const allSelectedLoading = hasSelectedModels.every(
      (modelId) =>
        eval_scores_loading[modelId] ||
        (!eval_scores_cache[modelId] && !eval_scores_errors[modelId]),
    )}
    {@const anyLoadedData = hasSelectedModels.some(
      (modelId) => eval_scores_cache[modelId],
    )}
    <div class="max-w-[1900px] mx-auto">
      {#if allSelectedLoading && !anyLoadedData && hasSelectedModels.length > 0}
        <!-- Big centered loading spinner when no data is loaded yet -->
        <div
          class="bg-white border border-gray-200 rounded-lg p-12 flex flex-col items-center justify-center min-h-[400px]"
        >
          <div class="loading loading-spinner loading-lg mb-4"></div>
          <div class="text-gray-600">Loading evaluation scores...</div>
        </div>
      {:else}
        <!-- Add Column Button - positioned above table on the right -->
        <div class="flex justify-end mb-4">
          {#if columns < 4}
            <button
              on:click={addColumn}
              class="btn btn-sm btn-outline gap-2"
              title="Add comparison column"
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                />
              </svg>
              Add Column
            </button>
          {/if}
        </div>

        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <!-- Model Selection Header Row -->
          <div
            class="grid border-b border-gray-200 bg-gray-50"
            style="grid-template-columns: 200px repeat({columns}, 1fr);"
          >
            <div class="px-6 py-4 font-semibold text-gray-900 flex items-start">
              <div class="flex items-center h-10">Compare</div>
            </div>
            {#each Array(columns) as _, i}
              <div class="px-6 py-4 relative min-w-0">
                {#if task}
                  <div class="flex items-center gap-1">
                    {#if columns > 2}
                      <button
                        on:click={() => removeColumn(i)}
                        class="w-6 h-6 rounded-full flex items-center justify-center hover:bg-gray-200 transition-colors flex-shrink-0"
                        title="Remove column"
                      >
                        ✕
                      </button>
                    {/if}
                    <div class="flex-1 min-w-0">
                      <SavedRunConfigurationsDropdown
                        title=""
                        {project_id}
                        current_task={task}
                        bind:selected_run_config_id={selectedModels[i]}
                        run_page={false}
                      />
                    </div>
                  </div>
                {/if}

                <!-- Show selected model info below dropdown -->
                {#if selectedModels[i]}
                  {@const selectedConfig = getSelectedRunConfig(
                    selectedModels[i],
                  )}
                  {#if selectedConfig}
                    {@const prompt_info_text =
                      getRunConfigPromptInfoText(selectedConfig)}
                    {@const prompt_link_url = prompt_link(
                      project_id,
                      task_id,
                      `task_run_config::${project_id}::${task_id}::${selectedConfig.id}`,
                    )}
                    <div class="mt-3 text-center">
                      <div class="font-semibold text-gray-900 text-sm">
                        {getDetailedModelName(selectedConfig, $model_info) ||
                          "Unknown Model"}
                      </div>
                      <div class="text-xs text-gray-500 font-normal mt-1">
                        {#if prompt_link_url}
                          Prompt: <a
                            href={prompt_link_url}
                            class="text-gray-500 font-normal link"
                          >
                            {getRunConfigPromptDisplayName(
                              selectedConfig,
                              $current_task_prompts,
                            )}
                          </a>
                        {:else}
                          Prompt: {getRunConfigPromptDisplayName(
                            selectedConfig,
                            $current_task_prompts,
                          )}
                        {/if}
                        {#if prompt_info_text}
                          <InfoTooltip
                            tooltip_text={prompt_info_text}
                            position="bottom"
                            no_pad={true}
                          />
                        {/if}
                      </div>
                    </div>
                  {/if}
                {/if}
              </div>
            {/each}
          </div>

          <!-- Comparison Data - only show if models are selected -->
          {#if hasSelectedModels.length > 0}
            {#each comparisonFeatures as section}
              <!-- Section Header -->
              <div class="bg-gray-50 px-6 py-3 border-b border-gray-200">
                <h4
                  class="text-sm font-semibold text-gray-900 uppercase tracking-wide"
                >
                  {section.category}
                </h4>
              </div>

              {#if section.items.length == 0}
                <div
                  class="grid gap-4 border-b border-gray-100 last:border-b-0"
                  style="grid-template-columns: 200px repeat(1, 1fr);"
                >
                  <!-- Empty section for visual consistency -->
                  <div
                    class="px-6 py-4 bg-gray-50 font-medium text-gray-700 flex items-center"
                  ></div>
                  <div class="px-6 py-4 text-center">
                    {#if section.has_default_eval_config === false}
                      <div>Select a default eval config to compare scores.</div>
                      <a
                        href={`/evals/${project_id}/${task_id}/${section.eval_id}/eval_configs`}
                        class="btn btn-xs rounded-full"
                      >
                        Manage Eval Configs
                      </a>
                    {:else}
                      Unknown issue - no scores found
                    {/if}
                  </div>
                </div>
              {/if}

              <!-- Section Rows -->
              {#if section.items.length > 0}
                <div
                  class="grid"
                  style="grid-template-columns: 200px repeat({columns}, 1fr);"
                >
                  {#each section.items as item, item_index}
                    <!-- Feature Label -->
                    <div
                      class="px-6 py-4 bg-gray-50 font-medium text-gray-700 flex items-center border-b border-gray-100"
                    >
                      {item.label}
                    </div>

                    <!-- Model Values -->
                    {#each Array(columns) as _, i}
                      {@const loading =
                        selectedModels[i] &&
                        eval_scores_loading[selectedModels[i]]}
                      {@const error =
                        selectedModels[i] &&
                        eval_scores_errors[selectedModels[i]]}
                      {@const percentComplete =
                        (selectedModels[i] &&
                          getModelPercentComplete(
                            selectedModels[i],
                            section.eval_id,
                          )) ||
                        0.0}
                      {#if selectedModels[i] && (loading || error || percentComplete < 1.0)}
                        <!-- These cells merge vertically for error states -->
                        {#if item_index === 0}
                          <div
                            class="px-6 py-4 text-center flex items-center justify-center border-b border-gray-100"
                            style="grid-row: span {section.items.length};"
                          >
                            {#if loading}
                              <!-- Column loading spinner -->
                              <div
                                class="loading loading-spinner loading-sm"
                              ></div>
                            {:else if error}
                              <!-- Error state -->
                              <span class="text-error text-sm">Error</span>
                            {:else if percentComplete < 1.0}
                              <div class="flex flex-col items-center gap-1">
                                <div class="text-warning text-sm font-medium">
                                  Eval Incomplete
                                </div>
                                <div class="text-left">
                                  <RunEval
                                    eval_id={section.eval_id}
                                    run_config_ids={[
                                      getSelectedRunConfig(selectedModels[i])
                                        ?.id || "",
                                    ]}
                                    {project_id}
                                    {task_id}
                                    current_eval_config_id={getModelDefaultEvalConfigID(
                                      selectedModels[i],
                                      section.eval_id,
                                    )}
                                    eval_type="run_configuration"
                                    btn_size="xs"
                                    btn_primary={false}
                                    on_run_complete={() => {
                                      // Clear cache and reload eval scores for this run config
                                      const runConfigId = selectedModels[i]
                                      if (runConfigId) {
                                        delete eval_scores_cache[runConfigId]
                                        delete eval_scores_errors[runConfigId]
                                        fetch_eval_scores(runConfigId)
                                      }
                                    }}
                                  />
                                </div>
                              </div>
                            {/if}
                          </div>
                        {/if}
                      {:else}
                        <div
                          class="px-6 py-4 text-center flex items-center justify-center border-b border-gray-100"
                        >
                          <!-- Normal value -->
                          <div class="flex flex-col items-center">
                            <span class="text-gray-900">
                              {getModelValue(selectedModels[i], item.key)}
                            </span>
                            {#if i > 0 && selectedModels[0] !== null}
                              {@const baseValue = getModelValue(
                                selectedModels[0],
                                item.key,
                              )}
                              {@const currentValue = getModelValue(
                                selectedModels[i],
                                item.key,
                              )}
                              {@const percentDiff = getPercentageDifference(
                                baseValue,
                                currentValue,
                              )}
                              {#if percentDiff}
                                <span class="text-xs text-gray-500 mt-1">
                                  {percentDiff}
                                </span>
                              {/if}
                            {/if}
                          </div>
                        </div>
                      {/if}
                    {/each}
                  {/each}
                </div>
              {/if}
            {/each}
          {:else}
            <!-- Empty state message within the table -->
            <div class="px-6 py-12 text-center text-gray-500">
              <svg
                class="mx-auto h-12 w-24 text-gray-400 mb-4"
                viewBox="0 0 1730 800"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M140 400C140 283.438 140 225.159 158.148 180.638C174.11 141.477 199.582 109.638 230.911 89.6844C266.527 67 313.151 67 406.4 67H539.6C632.85 67 679.473 67 715.091 89.6844C746.42 109.638 771.891 141.477 787.852 180.638C806 225.159 806 283.438 806 400C806 516.562 806 574.842 787.852 619.364C771.891 658.525 746.42 690.364 715.091 710.314C679.473 733 632.85 733 539.6 733H406.4C313.151 733 266.527 733 230.911 710.314C199.582 690.364 174.11 658.525 158.148 619.364C140 574.842 140 516.562 140 400Z"
                  stroke="currentColor"
                  stroke-width="50"
                />
                <path
                  d="M924 400C924 283.438 924 225.159 942.148 180.638C958.11 141.477 983.582 109.638 1014.91 89.6844C1050.53 67 1097.15 67 1190.4 67H1323.6C1416.85 67 1463.47 67 1499.09 89.6844C1530.42 109.638 1555.89 141.477 1571.85 180.638C1590 225.159 1590 283.438 1590 400C1590 516.562 1590 574.842 1571.85 619.364C1555.89 658.525 1530.42 690.364 1499.09 710.314C1463.47 733 1416.85 733 1323.6 733H1190.4C1097.15 733 1050.53 733 1014.91 710.314C983.582 690.364 958.11 658.525 942.148 619.364C924 574.842 924 516.562 924 400Z"
                  stroke="currentColor"
                  stroke-width="50"
                  stroke-dasharray="100 100"
                />
              </svg>
              <div class="text-lg font-medium text-gray-900 mb-2">
                Select run configurations to compare
              </div>
              <div class="text-gray-500">
                Choose run configurations from the dropdowns above to see a
                detailed comparison
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</AppPage>

<CreateNewRunConfigDialog
  bind:this={create_new_run_config_dialog}
  {project_id}
  {task}
  new_run_config_created={(run_config) => {
    if (
      target_new_run_config_col !== null &&
      target_new_run_config_col < columns
    ) {
      selectedModels[target_new_run_config_col] = run_config.id || null
    }
    target_new_run_config_col = null
  }}
  on:close={() => {
    if (
      target_new_run_config_col !== null &&
      target_new_run_config_col < columns
    ) {
      selectedModels[target_new_run_config_col] = null
    }
    target_new_run_config_col = null
  }}
/>
