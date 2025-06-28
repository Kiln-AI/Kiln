<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { TaskRunConfig } from "$lib/types"
  import {
    model_info,
    load_model_info,
    model_name,
    provider_name_from_id,
    current_task_prompts,
    load_available_prompts,
  } from "$lib/stores"
  import {
    getRunConfigPromptDisplayName,
    getRunConfigPromptInfoText,
  } from "$lib/utils/run_config_formatters"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  // State management
  let columns = 2 // Start with 2 columns
  let selectedModels: (string | null)[] = [null, null] // Track selected model for each column

  // Run configs state
  let task_run_configs: TaskRunConfig[] | null = null
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    await Promise.all([load_model_info(), load_available_prompts()])
    await get_task_run_configs()
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

  // Generate dropdown options from run configs
  $: modelOptions = generateRunConfigOptions(task_run_configs)

  function generateRunConfigOptions(
    configs: TaskRunConfig[] | null,
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
        const promptName = getRunConfigPromptDisplayName(
          config,
          $current_task_prompts,
        )

        return {
          label: `${modelName} • ${promptName}`, // First line: model name + prompt name
          value: config.id || "",
          description: getRunConfigPromptDisplayName(
            config,
            $current_task_prompts,
          ), // Second line: run config name
        }
      }),
    }))
  }

  // Mock comparison features/metrics placeholder data
  const comparisonFeatures = [
    {
      category: "Performance",
      items: [
        { label: "Accuracy Score", key: "accuracy" },
        { label: "Response Time", key: "response_time" },
        { label: "Throughput", key: "throughput" },
      ],
    },
    {
      category: "Capabilities",
      items: [
        { label: "Context Length", key: "context_length" },
        { label: "Function Calling", key: "function_calling" },
        { label: "Code Generation", key: "code_generation" },
        { label: "Reasoning", key: "reasoning" },
      ],
    },
    {
      category: "Cost",
      items: [
        { label: "Input Cost (per 1K tokens)", key: "input_cost" },
        { label: "Output Cost (per 1K tokens)", key: "output_cost" },
      ],
    },
  ]

  // Mock data for different models - will be replaced with actual run config data
  const modelData: Record<string, Record<string, string>> = {}

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
    if (!modelKey || !modelData[modelKey]) return "—"
    return modelData[modelKey][dataKey] || "—"
  }

  function getSelectedRunConfig(modelKey: string | null): TaskRunConfig | null {
    if (!modelKey || !task_run_configs) return null
    return task_run_configs.find((config) => config.id === modelKey) || null
  }
</script>

<AppPage
  title="Compare Run Methods"
  subtitle="Use evals to find the best run method for your task"
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
      <div
        class="grid gap-4 mb-8"
        style="grid-template-columns: repeat({columns}, 1fr) {columns < 4
          ? 'auto'
          : ''};"
      >
        {#each Array(columns) as _, i}
          <div class="bg-white border border-gray-200 rounded-lg p-6 relative">
            {#if columns > 2}
              <button
                on:click={() => removeColumn(i)}
                class="absolute top-2 right-2 w-6 h-6 rounded-full bg-red-100 hover:bg-red-200 flex items-center justify-center text-red-600 text-sm font-bold"
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
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <!-- Model Names Header -->
          <div
            class="grid gap-4 border-b border-gray-200 bg-gray-50"
            style="grid-template-columns: 200px repeat({columns}, 1fr);"
          >
            <div class="px-6 py-4 font-semibold text-gray-900">Run Method</div>
            {#each Array(columns) as _, i}
              {@const selectedConfig = getSelectedRunConfig(selectedModels[i])}
              <div class="px-6 py-4 text-center">
                {#if selectedConfig}
                  {@const prompt_info_text =
                    getRunConfigPromptInfoText(selectedConfig)}
                  <div class="font-semibold text-gray-900">
                    {model_name(
                      selectedConfig.run_config_properties?.model_name,
                      $model_info,
                    ) || "Unknown Model"}
                  </div>
                  <div class="text-sm text-gray-500 font-normal">
                    {getRunConfigPromptDisplayName(
                      selectedConfig,
                      $current_task_prompts,
                    )}
                    {#if prompt_info_text}
                      <InfoTooltip
                        tooltip_text={prompt_info_text}
                        position="bottom"
                        no_pad={true}
                      />
                    {/if}
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
                    <span class="text-gray-900">
                      {getModelValue(selectedModels[i], item.key)}
                    </span>
                  </div>
                {/each}
              </div>
            {/each}
          {/each}
        </div>
      {:else}
        <!-- Empty State -->
        <div
          class="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-12 text-center"
        >
          <svg
            class="mx-auto h-12 w-12 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 00-2-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
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
