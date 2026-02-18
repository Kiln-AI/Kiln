<script lang="ts">
  import * as echarts from "echarts"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type {
    TaskRunConfig,
    ProviderModels,
    PromptResponse,
  } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import {
    getDetailedModelName,
    getRunConfigPromptDisplayName,
  } from "$lib/utils/run_config_formatters"
  import { provider_name_from_id } from "$lib/stores"
  import ChartNoData from "./chart_no_data.svelte"

  // Type for comparison features (same as parent page)
  type ComparisonFeature = {
    category: string
    items: { label: string; key: string }[]
    has_default_eval_config: boolean | undefined
    eval_id: string
  }

  // Props
  export let comparisonFeatures: ComparisonFeature[]
  export let getModelValueRaw: (
    modelKey: string | null,
    dataKey: string,
  ) => number | null
  export let run_configs: TaskRunConfig[]
  export let model_info: ProviderModels | null
  export let prompts: PromptResponse | null = null
  export let loading: boolean = false

  // Axis selection state
  let selectedXAxis: string | null = null
  let selectedYAxis: string | null = null

  // Chart instance
  let chartInstance: echarts.ECharts | null = null

  // Convert comparisonFeatures to OptionGroup[] for dropdowns
  $: axisOptions = comparisonFeatures.map(
    (section): OptionGroup => ({
      label: section.category,
      options: section.items.map((item) => ({
        label: item.label,
        value: item.key,
      })),
    }),
  )

  // Set default axes when options become available
  $: if (axisOptions.length > 0) {
    // Default X to last section's last item (typically cost)
    if (selectedXAxis === null) {
      const lastSection = axisOptions[axisOptions.length - 1]
      if (lastSection && lastSection.options.length > 0) {
        selectedXAxis = lastSection.options[lastSection.options.length - 1]
          .value as string
      }
    }
    // Default Y to first section's first item (typically first eval)
    if (selectedYAxis === null && axisOptions.length > 0) {
      const firstSection = axisOptions[0]
      if (firstSection && firstSection.options.length > 0) {
        selectedYAxis = firstSection.options[0].value as string
      }
    }
  }

  // Get simple display name for the series (used as the internal name/key)
  function getRunConfigDisplayName(config: TaskRunConfig): string {
    return config.name || getDetailedModelName(config, model_info) || "Unknown"
  }

  // Build a map from display name to full legend text (name, model, prompt)
  function buildLegendFormatter(): Record<string, string> {
    const formatter: Record<string, string> = {}
    for (const config of run_configs) {
      if (!config.id) continue

      const displayName = getRunConfigDisplayName(config)
      const modelName = getDetailedModelName(config, model_info) || "Unknown"
      const promptName = getRunConfigPromptDisplayName(config, prompts)

      // Multi-line legend: display name on first line, model and prompt on 2nd/3rd
      formatter[displayName] =
        `${displayName}\n{sub|Model: ${modelName}}\n{sub|Prompt: ${promptName}}`
    }
    return formatter
  }

  function getAxisLabel(dataKey: string | null): string {
    if (!dataKey) return ""

    // Find the label from axisOptions
    for (const group of axisOptions) {
      const option = group.options.find((opt) => opt.value === dataKey)
      if (option) {
        return option.label
      }
    }

    return dataKey
  }

  function formatValue(value: number, dataKey: string): string {
    if (dataKey.includes("mean_cost")) {
      return `$${value.toFixed(6)}`
    }
    if (dataKey.includes("tokens")) {
      return value.toFixed(0)
    }
    return value.toFixed(2)
  }

  function getRunConfigById(configId: string): TaskRunConfig | null {
    return run_configs.find((c) => c.id === configId) || null
  }

  function generateChartData(): {
    series: echarts.SeriesOption[]
    legend: string[]
  } {
    const series: echarts.SeriesOption[] = []
    const legend: string[] = []

    if (!selectedXAxis || !selectedYAxis) {
      return { series, legend }
    }

    const xAxis = selectedXAxis
    const yAxis = selectedYAxis

    run_configs.forEach((config) => {
      const configId = config.id
      if (!configId) return

      const xValue = getModelValueRaw(configId, xAxis)
      const yValue = getModelValueRaw(configId, yAxis)

      // Only include if both values are available
      if (xValue !== null && yValue !== null) {
        const name = getRunConfigDisplayName(config)
        legend.push(name)

        series.push({
          name,
          type: "scatter",
          data: [[xValue, yValue, configId]],
          symbolSize: 15,
          emphasis: {
            scale: 2,
          },
        })
      }
    })

    return { series, legend }
  }

  function updateChart() {
    if (!chartInstance || !selectedXAxis || !selectedYAxis) return

    const xAxis = selectedXAxis
    const yAxis = selectedYAxis
    const { series, legend } = generateChartData()
    const legendFormatter = buildLegendFormatter()

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "item",
          formatter: function (params: {
            seriesName: string
            value: (number | string)[]
          }) {
            const xLabel = getAxisLabel(xAxis)
            const yLabel = getAxisLabel(yAxis)
            const configId = params.value[2] as string
            const config = getRunConfigById(configId)

            let tooltipHtml = `<strong>${params.seriesName}</strong>`

            if (config) {
              const modelName = getDetailedModelName(config, model_info)
              tooltipHtml = `<strong>${modelName}</strong>`
              if (isKilnAgentRunConfig(config.run_config_properties)) {
                const providerName = provider_name_from_id(
                  config.run_config_properties.model_provider_name,
                )
                const promptName = getRunConfigPromptDisplayName(
                  config,
                  prompts,
                )
                tooltipHtml += `<br/><span style="color: #666;">Provider:</span> ${providerName}`
                tooltipHtml += `<br/><span style="color: #666;">Prompt:</span> ${promptName}`
              }
            }

            tooltipHtml += `<br/><br/><span style="color: #666;">${xLabel}:</span> ${formatValue(params.value[0] as number, xAxis)}`
            tooltipHtml += `<br/><span style="color: #666;">${yLabel}:</span> ${formatValue(params.value[1] as number, yAxis)}`

            return tooltipHtml
          },
        },
        legend: {
          data: legend,
          orient: "vertical",
          left: "70%",
          top: "middle",
          itemGap: 16,
          formatter: (name: string) => legendFormatter[name] || name,
          textStyle: {
            lineHeight: 16,
            rich: {
              sub: {
                fontSize: 11,
                color: "#666",
                lineHeight: 14,
              },
            },
          },
        },
        grid: {
          right: "34%",
          left: 60,
          bottom: 50,
        },
        xAxis: {
          type: "value",
          name: getAxisLabel(selectedXAxis),
          nameLocation: "middle",
          nameGap: 35,
          scale: true,
          nameTextStyle: {
            fontSize: 14,
            fontWeight: 500,
          },
          axisLabel: {
            fontSize: 13,
          },
        },
        yAxis: {
          type: "value",
          name: getAxisLabel(selectedYAxis),
          nameLocation: "middle",
          nameGap: 50,
          scale: true,
          nameTextStyle: {
            fontSize: 14,
            fontWeight: 500,
          },
          axisLabel: {
            fontSize: 13,
          },
        },
        series,
      },
      true,
    )
  }

  // Reactive check for whether we have any data points to display
  $: hasDataPoints = (() => {
    if (!selectedXAxis || !selectedYAxis) return false
    const { series } = generateChartData()
    return series.length > 0
  })()

  // Update chart when selections or data change
  $: if (chartInstance && selectedXAxis && selectedYAxis) {
    updateChart()
  }

  // Also update when comparisonFeatures changes (data loaded)
  $: if (chartInstance && comparisonFeatures) {
    updateChart()
  }

  // Svelte action to initialize chart when element is added to DOM
  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)

    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    resizeObserver.observe(node)

    // Add legend hover interaction to highlight corresponding chart points
    chartInstance.on("mouseover", "legendItem", (params: { name: string }) => {
      chartInstance?.dispatchAction({
        type: "highlight",
        seriesName: params.name,
      })
    })

    chartInstance.on("mouseout", "legendItem", (params: { name: string }) => {
      chartInstance?.dispatchAction({
        type: "downplay",
        seriesName: params.name,
      })
    })

    updateChart()

    return {
      destroy() {
        resizeObserver.disconnect()
        chartInstance?.dispose()
        chartInstance = null
      },
    }
  }
</script>

<div class="bg-white border border-gray-200 rounded-lg p-6 mb-6">
  <div class="flex flex-col gap-6">
    <!-- Axis Selection Controls -->
    <div class="flex flex-row gap-8 flex-shrink-0 items-center">
      <div class="flex-grow">
        <div class="text-xl font-bold">Metric Correlation</div>

        <div class="text-sm text-gray-500 mb-4">
          Compare all run configurations by any two metrics.
        </div>
      </div>
      {#if !loading && axisOptions.length > 1}
        <div class="flex flex-row gap-2 items-center">
          <label
            for="x-axis-select"
            class="text-sm font-medium text-gray-700 mb-1 whitespace-nowrap"
          >
            X-Axis
          </label>
          <FancySelect
            aria_label="Select X-Axis metric"
            options={axisOptions}
            bind:selected={selectedXAxis}
            empty_label="Select metric"
          />
        </div>
        <div class="flex flex-row gap-2 items-center">
          <label
            for="y-axis-select"
            class="text-sm font-medium text-gray-700 mb-1 whitespace-nowrap"
          >
            Y-Axis
          </label>
          <FancySelect
            aria_label="Select Y-Axis metric"
            options={axisOptions}
            bind:selected={selectedYAxis}
            empty_label="Select metric"
          />
        </div>
      {/if}
    </div>

    <!-- Chart Container -->
    <div class="flex-1 min-w-0">
      {#if loading}
        <div
          class="flex items-center justify-center h-[400px] text-gray-500 gap-2"
        >
          <div class="loading loading-spinner loading-md"></div>
          <span>Loading chart data...</span>
        </div>
      {:else if axisOptions.length <= 1 || !hasDataPoints}
        <ChartNoData />
      {:else}
        <div use:initChart class="w-full h-[400px] xl:h-[600px] m-4"></div>
      {/if}
    </div>
  </div>
</div>
