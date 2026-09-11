// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"
import type { TaskRunConfig, ProviderModels, PromptResponse } from "$lib/types"

type Indicator = { name: string; max: number }
type SeriesDatum = { name: string; value: (number | null)[] }

type RadarOption = {
  tooltip: {
    trigger: string
    confine: boolean
    formatter: (params: { name: string }) => string
  }
  legend: {
    data: string[]
    formatter: (name: string) => string
    tooltip: {
      show: boolean
      formatter: (params: { name: string }) => string
    }
    textStyle: Record<string, unknown>
    orient: string
    itemGap: number
    bottom?: number
    top?: string
    left?: string
  }
  radar: {
    indicator: Indicator[]
    center: string[]
    radius: string
    axisName: { width: number }
  }
  series: {
    name: string
    type: string
    data: SeriesDatum[]
    areaStyle?: { opacity: number }
  }[]
}

const { setOptionCalls } = vi.hoisted(() => ({
  setOptionCalls: [] as RadarOption[],
}))

vi.mock("echarts", () => ({
  init: () => ({
    setOption: (option: RadarOption) => {
      setOptionCalls.push(option)
    },
    clear: () => {},
    dispose: () => {},
    resize: () => {},
  }),
}))

const CompareRadarChart = (await import("./compare_radar_chart.svelte")).default

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(
      globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }
    ).ResizeObserver = ResizeObserverStub
  }
})

afterEach(() => {
  cleanup()
})

type ComparisonFeature = {
  category: string
  items: { label: string; key: string }[]
  has_default_eval_config: boolean | undefined
  eval_id: string
}

type RadarProps = {
  comparisonFeatures: ComparisonFeature[]
  getModelValueRaw: (modelKey: string | null, dataKey: string) => number | null
  run_configs: TaskRunConfig[]
  model_info: ProviderModels | null
  prompts: PromptResponse | null
  selectedRunConfigIds: string[]
  scoreAxisMaxes: Record<string, number>
  metricLabels: Record<string, string>
}

type ValueTable = Record<string, Record<string, number | null>>

function lookup(values: ValueTable) {
  return (modelKey: string | null, dataKey: string): number | null => {
    if (!modelKey) return null
    const row = values[modelKey]
    if (!row) return null
    const value = row[dataKey]
    return value === undefined ? null : value
  }
}

const MODEL_INFO = {
  models: {
    gpt_4o: { id: "gpt_4o", name: "GPT 4o" },
    claude_sonnet: { id: "claude_sonnet", name: "Claude Sonnet" },
  },
} as unknown as ProviderModels

const PROMPTS = {
  prompts: [{ id: "custom_prompt", name: "Detailed Prompt" }],
  generators: [{ id: "simple_prompt_builder", name: "Basic (Zero Shot)" }],
} as unknown as PromptResponse

const FAST_CONFIG = {
  id: "rc_fast",
  v: 1,
  name: "Fast Config",
  model_type: "task_run_config",
  starred: false,
  run_config_properties: {
    type: "kiln_agent",
    model_name: "gpt_4o",
    model_provider_name: "openai",
    prompt_id: "simple_prompt_builder",
    top_p: 1,
    temperature: 1,
    structured_output_mode: "json_schema",
  },
} as unknown as TaskRunConfig

const THOROUGH_CONFIG = {
  id: "rc_thorough",
  v: 1,
  name: "Thorough Config",
  model_type: "task_run_config",
  starred: false,
  run_config_properties: {
    type: "kiln_agent",
    model_name: "claude_sonnet",
    model_provider_name: "anthropic",
    prompt_id: "custom_prompt",
    top_p: 1,
    temperature: 1,
    structured_output_mode: "json_schema",
    input_transform: { type: "jinja", template: "{{ task_input }}" },
  },
} as unknown as TaskRunConfig

const TOOL_CONFIG = {
  id: "rc_tool",
  v: 1,
  name: "",
  model_type: "task_run_config",
  starred: false,
  run_config_properties: {
    type: "mcp",
    tool_reference: {
      tool_id: "mcp::ticketing::route",
      tool_name: "Ticket Router",
    },
  },
} as unknown as TaskRunConfig

const TWIN_CONFIG = {
  ...FAST_CONFIG,
  id: "rc_twin",
  name: "Fast Config",
} as unknown as TaskRunConfig

const EVAL_SECTION: ComparisonFeature = {
  category: "Ticket Quality",
  eval_id: "eval_1",
  has_default_eval_config: true,
  items: [
    { label: "Pass Rate", key: "eval_1::pass_rate" },
    { label: "Overall Rating", key: "eval_1::overall_rating" },
    { label: "Custom Depth", key: "eval_1::custom_depth" },
  ],
}

const USAGE_SECTION: ComparisonFeature = {
  category: "Average Usage, Cost & Latency",
  eval_id: "kiln_cost_section",
  has_default_eval_config: undefined,
  items: [
    { label: "Total Tokens", key: "cost::mean_total_tokens" },
    { label: "Cost (USD)", key: "cost::mean_cost" },
    { label: "Latency", key: "cost::mean_total_llm_latency_ms" },
  ],
}

const SCORE_AXIS_MAXES = {
  "eval_1::pass_rate": 1,
  "eval_1::overall_rating": 5,
}

const METRIC_LABELS = {
  "eval_1::overall_rating": "Answer Quality",
  "cost::mean_total_llm_latency_ms": "Response Time",
}

const BASE_VALUES: ValueTable = {
  rc_fast: {
    "eval_1::pass_rate": 0.8,
    "eval_1::overall_rating": 4,
    "eval_1::custom_depth": 2,
    "cost::mean_total_tokens": 900,
    "cost::mean_cost": 0.002,
    "cost::mean_total_llm_latency_ms": 1200,
    "cost::mean_input_tokens": 600,
    "cost::mean_output_tokens": 300,
  },
  rc_thorough: {
    "eval_1::pass_rate": 0.6,
    "eval_1::overall_rating": 5,
    "eval_1::custom_depth": 3,
    "cost::mean_total_tokens": 2100,
    "cost::mean_cost": 0.006,
    "cost::mean_total_llm_latency_ms": 3000,
    "cost::mean_input_tokens": 1500,
    "cost::mean_output_tokens": 600,
  },
  rc_tool: {
    "eval_1::pass_rate": 1,
    "eval_1::overall_rating": 3,
    "eval_1::custom_depth": 1,
    "cost::mean_total_tokens": 1500,
    "cost::mean_cost": 0.004,
    "cost::mean_total_llm_latency_ms": 600,
    "cost::mean_input_tokens": 1000,
    "cost::mean_output_tokens": 500,
  },
  rc_twin: {
    "eval_1::pass_rate": 0.5,
    "eval_1::overall_rating": 2,
    "eval_1::custom_depth": 1.5,
    "cost::mean_total_tokens": 4000,
    "cost::mean_cost": 0.009,
    "cost::mean_total_llm_latency_ms": 5000,
  },
}

const MISSING_VALUES: ValueTable = {
  ...BASE_VALUES,
  rc_tool: { ...BASE_VALUES.rc_tool, "eval_1::custom_depth": null },
}

const MANY_SCORE_KEYS = Array.from(
  { length: 12 },
  (_, index) => `eval_1::score_${String(index + 1).padStart(2, "0")}`,
)

const MANY_SCORE_SECTION: ComparisonFeature = {
  category: "Ticket Quality",
  eval_id: "eval_1",
  has_default_eval_config: true,
  items: MANY_SCORE_KEYS.map((key, index) => ({
    key,
    label: `Score ${String(index + 1).padStart(2, "0")}`,
  })),
}

const MANY_SCORE_VALUES: ValueTable = Object.fromEntries(
  ["rc_fast", "rc_thorough", "rc_tool"].map((configId, configIndex) => [
    configId,
    {
      ...Object.fromEntries(
        MANY_SCORE_KEYS.map((key, scoreIndex) => [
          key,
          0.05 * (scoreIndex + 1) + 0.01 * configIndex,
        ]),
      ),
      "cost::mean_total_tokens": BASE_VALUES[configId][
        "cost::mean_total_tokens"
      ] as number,
      "cost::mean_cost": BASE_VALUES[configId]["cost::mean_cost"] as number,
      "cost::mean_total_llm_latency_ms": BASE_VALUES[configId][
        "cost::mean_total_llm_latency_ms"
      ] as number,
    },
  ]),
)

const three_configs: RadarProps = {
  comparisonFeatures: [EVAL_SECTION, USAGE_SECTION],
  getModelValueRaw: lookup(BASE_VALUES),
  run_configs: [FAST_CONFIG, THOROUGH_CONFIG, TOOL_CONFIG],
  model_info: MODEL_INFO,
  prompts: PROMPTS,
  selectedRunConfigIds: ["rc_fast", "rc_thorough", "rc_tool"],
  scoreAxisMaxes: SCORE_AXIS_MAXES,
  metricLabels: METRIC_LABELS,
}

const missing_result: RadarProps = {
  ...three_configs,
  getModelValueRaw: lookup(MISSING_VALUES),
}

const two_configs: RadarProps = {
  ...three_configs,
  selectedRunConfigIds: ["rc_fast", "rc_thorough"],
}

const single_config: RadarProps = {
  ...three_configs,
  selectedRunConfigIds: ["rc_fast"],
}

const many_scores: RadarProps = {
  comparisonFeatures: [MANY_SCORE_SECTION, USAGE_SECTION],
  getModelValueRaw: lookup(MANY_SCORE_VALUES),
  run_configs: [FAST_CONFIG, THOROUGH_CONFIG, TOOL_CONFIG],
  model_info: MODEL_INFO,
  prompts: PROMPTS,
  selectedRunConfigIds: ["rc_fast", "rc_thorough", "rc_tool"],
  scoreAxisMaxes: {},
  metricLabels: {},
}

const duplicate_names: RadarProps = {
  ...three_configs,
  run_configs: [FAST_CONFIG, TWIN_CONFIG],
  selectedRunConfigIds: ["rc_fast", "rc_twin"],
}

const fixtures = {
  three_configs,
  missing_result,
  two_configs,
  single_config,
  many_scores,
  duplicate_names,
}

function renderChart(props: RadarProps) {
  cleanup()
  setOptionCalls.length = 0
  return render(CompareRadarChart, { props })
}

async function captureOption(
  props: RadarProps,
  { fullScale = false }: { fullScale?: boolean } = {},
): Promise<RadarOption> {
  const { getByRole } = renderChart(props)
  await tick()
  await tick()
  if (fullScale) {
    await fireEvent.click(getByRole("button", { name: "Full Scale" }))
    await tick()
  }
  return setOptionCalls[setOptionCalls.length - 1]
}

function byName(names: string[], render_one: (name: string) => string) {
  return Object.fromEntries(names.map((name) => [name, render_one(name)]))
}

function serialise(option: RadarOption): Record<string, unknown> {
  const names = Array.from(new Set(option.legend.data))
  const copy = JSON.parse(JSON.stringify(option)) as Record<string, unknown>
  const tooltip = copy.tooltip as Record<string, unknown>
  tooltip.formatter = byName(names, (name) =>
    option.tooltip.formatter({ name }),
  )
  const legend = copy.legend as Record<string, unknown>
  legend.formatter = byName(names, (name) => option.legend.formatter(name))
  const legendTooltip = legend.tooltip as Record<string, unknown>
  legendTooltip.formatter = byName(names, (name) =>
    option.legend.tooltip.formatter({ name }),
  )
  return copy
}

function axisNames(option: RadarOption): string[] {
  return option.radar.indicator.map((indicator) => indicator.name)
}

function axisMax(option: RadarOption, name: string): number {
  const indicator = option.radar.indicator.find((i) => i.name === name)
  if (!indicator) throw new Error(`no axis named ${name}`)
  return indicator.max
}

function valueOn(
  option: RadarOption,
  seriesName: string,
  axisName: string,
): number | null {
  const datum = option.series[0].data.find((d) => d.name === seriesName)
  if (!datum) throw new Error(`no series named ${seriesName}`)
  const index = axisNames(option).indexOf(axisName)
  if (index < 0) throw new Error(`no axis named ${axisName}`)
  return datum.value[index]
}

function tooltipFor(option: RadarOption, seriesName: string): string {
  return option.tooltip.formatter({ name: seriesName })
}

describe("compare radar chart axes", () => {
  it("lists the eval score axes first and the usage axes after them", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(axisNames(option)).toEqual([
      "Pass Rate",
      "Answer Quality",
      "Custom Depth",
      "Token Efficiency",
      "Cost Efficiency",
      "Response Time",
    ])
  })

  it("names usage axes for the direction that is better", async () => {
    const option = await captureOption(fixtures.many_scores)
    expect(axisNames(option)).toContain("Token Efficiency")
    expect(axisNames(option)).toContain("Cost Efficiency")
    expect(axisNames(option)).toContain("Speed")
  })

  it("uses the display name the user gave a row, on the axis, in the tooltip, and over the built-in usage name", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(axisNames(option)).toContain("Answer Quality")
    expect(axisNames(option)).not.toContain("Overall Rating")
    expect(tooltipFor(option, "Fast Config")).toContain(
      "<div>Answer Quality: 4.000</div>",
    )
    expect(axisNames(option)).toContain("Response Time")
    expect(axisNames(option)).not.toContain("Speed")
  })

  it("leaves out a usage axis whose row is hidden in the comparison table", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(axisNames(option)).not.toContain("Input Token Efficiency")
    expect(axisNames(option)).not.toContain("Output Token Efficiency")
    expect(option.radar.indicator).toHaveLength(6)
  })

  it("leaves out a score that any plotted run config has no result for, and counts it under the title", async () => {
    const option = await captureOption(fixtures.missing_result)
    expect(axisNames(option)).not.toContain("Custom Depth")
    expect(option.radar.indicator).toHaveLength(5)

    const { container } = renderChart(fixtures.missing_result)
    await tick()
    expect(container.textContent).toContain(
      "Not shown: 1 axis without results for every selected run config. See the table above.",
    )
  })
})

describe("compare radar chart axis maximums", () => {
  it("pads the highest value in the data by ten percent in relative mode", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(axisMax(option, "Pass Rate")).toBeCloseTo(1.1, 10)
    expect(axisMax(option, "Answer Quality")).toBeCloseTo(5.5, 10)
    expect(axisMax(option, "Custom Depth")).toBeCloseTo(3.3, 10)
  })

  it("uses the score's own range in full scale mode, and the padded data maximum where the range is unknown", async () => {
    const option = await captureOption(fixtures.three_configs, {
      fullScale: true,
    })
    expect(axisMax(option, "Pass Rate")).toBe(1)
    expect(axisMax(option, "Answer Quality")).toBe(5)
    expect(axisMax(option, "Custom Depth")).toBeCloseTo(3.3, 10)
  })

  it("keeps usage axes on a nought to one hundred scale in both modes", async () => {
    const relative = await captureOption(fixtures.three_configs)
    const full = await captureOption(fixtures.three_configs, {
      fullScale: true,
    })
    expect(axisMax(relative, "Cost Efficiency")).toBe(100)
    expect(axisMax(full, "Cost Efficiency")).toBe(100)
    expect(axisMax(full, "Response Time")).toBe(100)
  })
})

describe("compare radar chart series", () => {
  it("plots the raw score on an eval axis", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(valueOn(option, "Fast Config", "Pass Rate")).toBe(0.8)
    expect(valueOn(option, "Thorough Config", "Answer Quality")).toBe(5)
    expect(valueOn(option, "Ticket Router", "Custom Depth")).toBe(1)
  })

  it("scores the cheapest and the fastest run config highest on the usage axes", async () => {
    const option = await captureOption(fixtures.three_configs)
    const cheapest = valueOn(option, "Fast Config", "Cost Efficiency") ?? 0
    const dearest = valueOn(option, "Thorough Config", "Cost Efficiency") ?? 0
    expect(cheapest).toBeGreaterThan(dearest)

    const fastest = valueOn(option, "Ticket Router", "Response Time") ?? 0
    const slowest = valueOn(option, "Thorough Config", "Response Time") ?? 0
    expect(fastest).toBeGreaterThan(slowest)

    const fewestTokens = valueOn(option, "Fast Config", "Token Efficiency") ?? 0
    const mostTokens =
      valueOn(option, "Thorough Config", "Token Efficiency") ?? 0
    expect(fewestTokens).toBeGreaterThan(mostTokens)
  })

  it("puts every usage axis at the midpoint when there is nothing to compare against", async () => {
    const option = await captureOption(fixtures.single_config)
    expect(valueOn(option, "Fast Config", "Cost Efficiency")).toBe(50)
    expect(valueOn(option, "Fast Config", "Response Time")).toBe(50)
    expect(valueOn(option, "Fast Config", "Token Efficiency")).toBe(50)
  })

  it("fills the area only when a single run config is plotted", async () => {
    const one = await captureOption(fixtures.single_config)
    const several = await captureOption(fixtures.three_configs)
    expect(one.series[0].areaStyle).toEqual({ opacity: 0.2 })
    expect(several.series[0].areaStyle).toBeUndefined()
  })
})

describe("compare radar chart legend", () => {
  it("stands the legend beside the chart for more than two run configs", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(option.legend.orient).toBe("vertical")
    expect(option.legend.left).toBe("60%")
    expect(option.legend.top).toBe("middle")
    expect(option.radar.center).toEqual(["36%", "50%"])
    expect(option.radar.radius).toBe("70%")
  })

  it("leaves the left-hand axis names room on the card", async () => {
    // The plot is at its widest on a 1280px screen, where the card takes its
    // larger minimum height and echarts sizes the radius from that height.
    const cardWidth = 928
    const cardHeight = 620
    const nameGap = 15
    for (const props of [fixtures.three_configs, fixtures.two_configs]) {
      const option = await captureOption(props)
      const centreX = (parseFloat(option.radar.center[0]) / 100) * cardWidth
      const radius =
        (parseFloat(option.radar.radius) / 100) *
        (Math.min(cardWidth, cardHeight) / 2)
      expect(centreX - radius).toBeGreaterThan(
        option.radar.axisName.width + nameGap,
      )
    }
  })

  it("lays the legend under the chart for two or fewer run configs", async () => {
    const option = await captureOption(fixtures.two_configs)
    expect(option.legend.orient).toBe("horizontal")
    expect(option.legend.bottom).toBe(0)
    expect(option.legend.left).toBe("center")
    expect(option.radar.center).toEqual(["50%", "46%"])
    expect(option.radar.radius).toBe("62%")
  })

  it("writes the model, prompt and input transform under the run config name", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(option.legend.formatter("Fast Config")).toBe(
      "Fast Config\n{sub|Model: GPT 4o (OpenAI)}\n{sub|Prompt: Basic (Zero Shot)}",
    )
    expect(option.legend.formatter("Thorough Config")).toBe(
      "Thorough Config\n{sub|Model: Claude Sonnet (Anthropic)}\n{sub|Prompt: Detailed Prompt}\n{sub|Input Transform: Custom}",
    )
  })

  it("writes the tool name under an MCP run config", async () => {
    const option = await captureOption(fixtures.three_configs)
    expect(option.legend.data).toContain("Ticket Router")
    expect(option.legend.formatter("Ticket Router")).toBe(
      "Ticket Router\n{sub|Tool: Ticket Router}",
    )
    expect(
      option.legend.tooltip.formatter({ name: "Ticket Router" }),
    ).toContain("<div>MCP Tool: Ticket Router</div>")
  })
})

describe("compare radar chart tooltip", () => {
  it("lists the run config details and every score when there are ten or fewer", async () => {
    const option = await captureOption(fixtures.three_configs)
    const html = tooltipFor(option, "Fast Config")
    expect(html).toContain("<div>Model: GPT 4o (OpenAI)</div>")
    expect(html).toContain("<div>Prompt: Basic (Zero Shot)</div>")
    expect(html).toContain("<div>Mean Cost: $0.002000</div>")
    expect(html).toContain("<div>Mean Latency: 1.2s</div>")
    expect(html).toContain("<div>Mean Total Tokens: 900 tokens</div>")
    expect(html).toContain(">Values</div>")
    expect(html).toContain("<div>Pass Rate: 0.800</div>")
    expect(html).toContain("<div>Custom Depth: 2.000</div>")
    expect(html).not.toContain("Cost Efficiency:")
    expect(html).not.toContain("Token Efficiency:")
    expect(html).not.toContain("Response Time:")
  })

  it("lists only the ten weakest scores and counts the rest when there are more than ten", async () => {
    const option = await captureOption(fixtures.many_scores)
    const html = tooltipFor(option, "Fast Config")
    const lines = html.match(/<div>Score \d\d: /g) ?? []
    expect(lines).toHaveLength(10)
    expect(html).toContain(">Lowest Scores</div>")
    expect(html).toContain("<div>Score 01: 0.050</div>")
    expect(html).toContain("<div>Score 10: 0.500</div>")
    expect(html).not.toContain("Score 11:")
    expect(html).not.toContain("Score 12:")
    expect(html).toContain("+2 more in the table above")
  })

  it("escapes the score label in the tooltip", async () => {
    const option = await captureOption({
      ...fixtures.three_configs,
      metricLabels: { "eval_1::pass_rate": "<b>Boom</b>" },
    })
    const html = tooltipFor(option, "Fast Config")
    expect(html).toContain("<div>&lt;b&gt;Boom&lt;/b&gt;: 0.800</div>")
    expect(html).not.toContain("<b>Boom</b>")
  })

  it("keeps two run configs sharing a name apart", async () => {
    const option = await captureOption(fixtures.duplicate_names)
    expect(option.legend.data).toEqual(["Fast Config (1)", "Fast Config (2)"])

    const first = tooltipFor(option, "Fast Config (1)")
    expect(first).toContain("<div>Mean Cost: $0.002000</div>")
    expect(first).toContain("<div>Pass Rate: 0.800</div>")

    const second = tooltipFor(option, "Fast Config (2)")
    expect(second).toContain("<div>Mean Cost: $0.009000</div>")
    expect(second).toContain("<div>Pass Rate: 0.500</div>")
  })
})

describe("compare radar chart scale default", () => {
  it("defaults to full scale for a single run config and to relative scale for several", async () => {
    const one = renderChart(fixtures.single_config)
    await tick()
    expect(
      one
        .getByRole("button", { name: "Full Scale" })
        .getAttribute("aria-pressed"),
    ).toBe("true")
    expect(
      axisMax(setOptionCalls[setOptionCalls.length - 1], "Pass Rate"),
    ).toBe(1)

    const several = renderChart(fixtures.three_configs)
    await tick()
    expect(
      several
        .getByRole("button", { name: "Relative" })
        .getAttribute("aria-pressed"),
    ).toBe("true")
    expect(
      axisMax(setOptionCalls[setOptionCalls.length - 1], "Pass Rate"),
    ).toBeCloseTo(1.1, 10)
  })
})

describe("compare radar chart empty states", () => {
  it("draws nothing at all when the table has no rows left to offer", async () => {
    const { container } = renderChart({
      ...fixtures.three_configs,
      comparisonFeatures: [],
    })
    await tick()
    expect(container.textContent?.trim()).toBe("")
    expect(setOptionCalls).toHaveLength(0)
  })

  it("keeps the card and its empty state when hidden rows leave two axes", async () => {
    const { container } = renderChart({
      ...fixtures.three_configs,
      comparisonFeatures: [
        { ...EVAL_SECTION, items: EVAL_SECTION.items.slice(0, 2) },
      ],
    })
    await tick()
    expect(container.textContent).toContain("Radar Chart")
    expect(container.textContent).toContain("Not Enough Axes")
    expect(container.textContent).toContain(
      "A radar chart needs at least 3 axes. Show a hidden row, run the missing evals, or compare fewer run configurations.",
    )
    expect(setOptionCalls).toHaveLength(0)
  })

  it("shows the not enough axes state when the plotted configs share fewer than three", async () => {
    const { container } = renderChart({
      ...fixtures.three_configs,
      comparisonFeatures: [EVAL_SECTION],
      getModelValueRaw: lookup({
        ...BASE_VALUES,
        rc_tool: {
          ...BASE_VALUES.rc_tool,
          "eval_1::overall_rating": null,
          "eval_1::custom_depth": null,
        },
      }),
    })
    await tick()
    expect(container.textContent).toContain("Not Enough Axes")
    expect(container.textContent).toContain(
      "A radar chart needs at least 3 axes. Show a hidden row, run the missing evals, or compare fewer run configurations.",
    )
    expect(container.textContent).not.toContain("Not shown:")
    expect(setOptionCalls).toHaveLength(0)
  })

  it("asks for evals only when the table offers no eval section at all", async () => {
    const { container } = renderChart({
      ...fixtures.three_configs,
      comparisonFeatures: [USAGE_SECTION],
    })
    await tick()
    expect(container.textContent).toContain("No Data Available")
    expect(container.textContent).toContain(
      "Create and run evals to see a comparison chart.",
    )
    expect(container.textContent).not.toContain("Not shown:")
  })
})

const OPTION_KEYS = ["legend", "radar", "series", "tooltip"]

// Paths of every value the predicate rejects, named so a failure says where.
function offendingPaths(
  value: unknown,
  reject: (entry: unknown) => boolean,
  path = "option",
): string[] {
  if (reject(value)) return [path]
  if (Array.isArray(value)) {
    return value.flatMap((entry, index) =>
      offendingPaths(entry, reject, `${path}[${index}]`),
    )
  }
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).flatMap(
      ([key, entry]) => offendingPaths(entry, reject, `${path}.${key}`),
    )
  }
  return []
}

describe.each(Object.entries(fixtures))(
  "compare radar chart option shape (%s)",
  (_name, props) => {
    it("sets every part of the option, one value per axis, with no gaps", async () => {
      const option = await captureOption(props)

      expect(Object.keys(option).sort()).toEqual(OPTION_KEYS)

      const axisCount = option.radar.indicator.length
      expect(axisCount).toBeGreaterThan(0)
      for (const series of option.series) {
        expect(series.data.length).toBeGreaterThan(0)
        for (const datum of series.data) {
          expect(datum.value).toHaveLength(axisCount)
        }
      }

      const names = Array.from(new Set(option.legend.data))
      expect(names.length).toBeGreaterThan(0)
      for (const name of names) {
        expect(option.tooltip.formatter({ name })).not.toBe("")
        expect(option.legend.formatter(name)).not.toBe("")
        expect(option.legend.tooltip.formatter({ name })).not.toBe("")
      }

      // An undefined in an echarts option drops a setting without saying so, and a
      // formatter left behind by serialise() is one the golden dump cannot see.
      expect(offendingPaths(option, (entry) => entry === undefined)).toEqual([])
      expect(
        offendingPaths(
          serialise(option),
          (entry) => typeof entry === "function",
        ),
      ).toEqual([])
    })
  },
)
