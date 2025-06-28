<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type {
    AvailableModels,
    PromptResponse,
    TaskRunConfig,
  } from "$lib/types"
  import type { components } from "$lib/api_schema"

  type RunConfigEvalScoresSummary =
    components["schemas"]["RunConfigEvalScoresSummary"]
  type EvalConfigResult = components["schemas"]["EvalConfigResult"]
  type ScoreSummary = components["schemas"]["ScoreSummary"]
  import {
    model_info,
    load_model_info,
    model_name,
    provider_name_from_id,
    current_task_prompts,
    load_available_prompts,
    load_available_models,
    available_models,
  } from "$lib/stores"
  import {
    getRunConfigPromptDisplayName,
    getRunConfigPromptInfoText,
  } from "$lib/utils/run_config_formatters"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import { prompt_link } from "$lib/utils/link_builder"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  // State management
  let columns = 2 // Start with 2 columns
  let selectedModels: (string | null)[] = [null, null] // Track selected model for each column

  // Run configs state
  let task_run_configs: TaskRunConfig[] | null = null
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
    if (!task_run_configs) return

    const urlParams = new URLSearchParams($page.url.search)
    const urlModels = urlParams.get("models")

    if (urlModels) {
      const modelIds = urlModels.split(",").map((id) => (id === "" ? null : id))

      // Validate each model ID exists in task_run_configs
      for (let i = 0; i < Math.min(modelIds.length, columns); i++) {
        const modelId = modelIds[i]
        if (
          modelId &&
          task_run_configs.find((config) => config.id === modelId)
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
    // Initialize basic state from URL first (columns)
    initializeFromURL()

    // Load data needed for the page
    await Promise.all([
      load_model_info(),
      load_available_prompts(),
      load_available_models(),
    ])
    await get_task_run_configs()

    // Now that data is loaded, restore full state from URL
    restoreStateFromURL()

    // Mark initialization as complete
    isInitializing = false
  })

  async function get_task_run_configs() {
    try {
      loading = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/task_run_configs",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      task_run_configs = data
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
    }[] = []
    const evalCategories: Record<string, Set<string>> = {}

    // Collect all evals and their scores from selected models
    models.forEach((modelId) => {
      if (!modelId || !scores_cache[modelId]) return

      const evalScores = scores_cache[modelId]
      evalScores.eval_results.forEach((evalResult) => {
        if (!evalCategories[evalResult.eval_name]) {
          evalCategories[evalResult.eval_name] = new Set()
        }

        evalResult.eval_config_results.forEach((configResult) => {
          Object.keys(configResult.results).forEach((scoreKey) => {
            evalCategories[evalResult.eval_name].add(scoreKey)
          })
        })
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

      if (items.length > 0) {
        features.push({
          category: evalName,
          items,
        })
      }
    })

    // Add Cost section (always last)
    const costItems = [
      { label: "Input Tokens", key: "cost::mean_input_tokens" },
      { label: "Output Tokens", key: "cost::mean_output_tokens" },
      { label: "Total Tokens", key: "cost::mean_total_tokens" },
      { label: "Cost (USD)", key: "cost::mean_cost" },
    ]

    features.push({
      category: "Avg Usage",
      items: costItems,
    })

    return features
  }

  // Generate dropdown options from run configs
  $: modelOptions = generateRunConfigOptions(
    task_run_configs,
    $current_task_prompts,
    $available_models,
  )

  function generateRunConfigOptions(
    configs: TaskRunConfig[] | null,
    task_prompts: PromptResponse | null,
    _: AvailableModels[],
  ): OptionGroup[] {
    if (!configs || configs.length === 0) {
      return []
    }

    // Group by provider
    const providerGroups: Record<string, TaskRunConfig[]> = {}

    configs.forEach((config) => {
      const provider =
        provider_name_from_id(
          config.run_config_properties?.model_provider_name,
        ) || "Unknown Provider"
      if (!providerGroups[provider]) {
        providerGroups[provider] = []
      }
      providerGroups[provider].push(config)
    })

    return Object.entries(providerGroups).map(([provider, configs]) => ({
      label: provider,
      options: configs.map((config) => {
        const modelName =
          model_name(config.run_config_properties?.model_name, $model_info) ||
          "Unknown Model"
        const promptName = getRunConfigPromptDisplayName(config, task_prompts)

        return {
          label: `${modelName} • ${promptName}`, // First line: model name + prompt name
          value: config.id || "",
          description: config.name,
        }
      }),
    }))
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

    // Find the best available score from any eval config
    let bestScore: number | null = null
    let bestCompleteness = 0

    evalResult.eval_config_results.forEach((configResult: EvalConfigResult) => {
      const score: ScoreSummary | null = configResult.results[scoreKey]
      if (score && configResult.percent_complete > bestCompleteness) {
        bestScore = score.mean_score
        bestCompleteness = configResult.percent_complete
      }
    })

    if (bestScore !== null) {
      return (bestScore as number).toFixed(2)
    }

    return "—"
  }

  function getSelectedRunConfig(modelKey: string | null): TaskRunConfig | null {
    if (!modelKey || !task_run_configs) return null
    return task_run_configs.find((config) => config.id === modelKey) || null
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
      return compare > 0 ? "+∞%" : "-∞%"
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
</script>

<AppPage
  title="Compare Run Methods"
  subtitle="Compare run methods for your task using evals"
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Run Methods</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else}
    <div class="max-w-7xl mx-auto">
      <!-- Column Headers with Dropdowns -->
      <div class="flex flex-row flex-wrap gap-4 mb-8">
        {#each Array(columns) as _, i}
          <div
            class="bg-white border border-gray-200 rounded-lg p-6 relative flex-1 min-w-[200px] max-w-md"
          >
            {#if columns > 2}
              <button
                on:click={() => removeColumn(i)}
                class="absolute top-2 right-2 w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold"
                title="Remove column"
              >
                ×
              </button>
            {/if}

            <div class="mb-4">
              <div class="block text-sm font-medium text-gray-700 mb-2">
                Select Run Method {i + 1}
              </div>
              <FancySelect
                options={modelOptions}
                bind:selected={selectedModels[i]}
                empty_label="Choose a run method..."
              />
            </div>
          </div>
        {/each}

        <!-- Add Column Button -->
        {#if columns < 4}
          <div class="flex items-center justify-center">
            <button
              on:click={addColumn}
              class="w-16 h-16 rounded-full border-2 border-dashed border-gray-300 hover:border-gray-400 flex items-center justify-center text-gray-500 hover:text-gray-600 transition-colors"
              title="Add comparison column"
            >
              <svg
                class="w-8 h-8"
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
            </button>
          </div>
        {/if}
      </div>

      <!-- Comparison Table -->
      {#if selectedModels.some((model) => model !== null)}
        {@const hasSelectedModels = selectedModels.filter((m) => m !== null)}
        {@const allSelectedLoading = hasSelectedModels.every(
          (modelId) =>
            eval_scores_loading[modelId] ||
            (!eval_scores_cache[modelId] && !eval_scores_errors[modelId]),
        )}
        {@const anyLoadedData = hasSelectedModels.some(
          (modelId) => eval_scores_cache[modelId],
        )}

        {#if allSelectedLoading && !anyLoadedData}
          <!-- Big centered loading spinner when no data is loaded yet -->
          <div
            class="bg-white border border-gray-200 rounded-lg p-12 flex flex-col items-center justify-center min-h-[400px]"
          >
            <div class="loading loading-spinner loading-lg mb-4"></div>
            <div class="text-gray-600">Loading evaluation scores...</div>
          </div>
        {:else}
          <div
            class="bg-white border border-gray-200 rounded-lg overflow-hidden"
          >
            <!-- Model Names Header -->
            <div
              class="grid gap-4 border-b border-gray-200 bg-gray-50"
              style="grid-template-columns: 200px repeat({columns}, 1fr);"
            >
              <div class="px-6 py-4 font-semibold text-gray-900"></div>
              {#each Array(columns) as _, i}
                {@const selectedConfig = getSelectedRunConfig(
                  selectedModels[i],
                )}
                <div class="px-6 py-4 text-center overflow-hidden">
                  {#if selectedConfig}
                    {@const prompt_info_text =
                      getRunConfigPromptInfoText(selectedConfig)}
                    {@const prompt_link_url = prompt_link(
                      project_id,
                      task_id,
                      `task_run_config::${project_id}::${task_id}::${selectedConfig.id}`,
                    )}
                    <div class="font-semibold text-gray-900">
                      {model_name(
                        selectedConfig.run_config_properties?.model_name,
                        $model_info,
                      ) || "Unknown Model"}
                    </div>
                    <div class="text-sm text-gray-500 font-normal">
                      {#if prompt_link_url}
                        <a
                          href={prompt_link_url}
                          class="text-gray-500 font-normal link"
                        >
                          Prompt: {getRunConfigPromptDisplayName(
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
                    <div
                      class="badge bg-gray-200 text-gray-500 whitespace-nowrap"
                    >
                      {selectedConfig.name}
                    </div>
                  {:else}
                    <div class="font-semibold text-gray-900">—</div>
                  {/if}
                </div>
              {/each}
            </div>

            {#each comparisonFeatures as section}
              <!-- Section Header -->
              <div class="bg-gray-50 px-6 py-3 border-b border-gray-200">
                <h4
                  class="text-sm font-semibold text-gray-900 uppercase tracking-wide"
                >
                  {section.category}
                </h4>
              </div>

              <!-- Section Rows -->
              {#each section.items as item}
                <div
                  class="grid gap-4 border-b border-gray-100 last:border-b-0"
                  style="grid-template-columns: 200px repeat({columns}, 1fr);"
                >
                  <!-- Feature Label -->
                  <div
                    class="px-6 py-4 bg-gray-50 font-medium text-gray-700 flex items-center"
                  >
                    {item.label}
                  </div>

                  <!-- Model Values -->
                  {#each Array(columns) as _, i}
                    <div
                      class="px-6 py-4 text-center flex items-center justify-center"
                    >
                      {#if selectedModels[i] && eval_scores_loading[selectedModels[i]]}
                        <!-- Column loading spinner -->
                        <div class="loading loading-spinner loading-sm"></div>
                      {:else if selectedModels[i] && eval_scores_errors[selectedModels[i]]}
                        <!-- Error state -->
                        <span class="text-error text-sm">Error</span>
                      {:else}
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
                      {/if}
                    </div>
                  {/each}
                </div>
              {/each}
            {/each}
          </div>
        {/if}
      {:else}
        <!-- Empty State -->
        <div
          class="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center"
        >
          <svg
            class="mx-auto h-12 w-24 text-gray-400"
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

          <h3 class="mt-4 text-lg font-medium text-gray-900">
            Select run methods to compare
          </h3>
          <p class="mt-2 text-gray-500">
            Choose run methods from the dropdowns above to see a detailed
            comparison
          </p>
        </div>
      {/if}
    </div>
  {/if}
</AppPage>
