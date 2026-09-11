import { describe, it, expect } from "vitest"
import {
  axisMaxFor,
  buildAxisLabels,
  buildRadarChartData,
  metricToScore,
  plottedRunConfigs,
  rankTooltipScores,
  runConfigSeriesNames,
  sharedAxisKeys,
  splitAxisKeys,
} from "./radar_chart_data"
import type { ComparisonFeature, RadarValueLookup } from "./radar_chart_data"
import type { TaskRunConfig } from "$lib/types"

function make_config(id: string, name: string): TaskRunConfig {
  return {
    id,
    name,
    run_config_properties: { type: "kiln_agent" },
  } as unknown as TaskRunConfig
}

const FAST = make_config("rc_fast", "Fast Config")
const THOROUGH = make_config("rc_thorough", "Thorough Config")
const IDLE = make_config("rc_idle", "Idle Config")

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
    { label: "Cost (USD)", key: "cost::mean_cost" },
    { label: "Latency", key: "cost::mean_total_llm_latency_ms" },
    { label: "Total Tokens", key: "cost::mean_total_tokens" },
  ],
}

type ValueTable = Record<string, Record<string, number | null>>

const VALUES: ValueTable = {
  rc_fast: {
    "eval_1::pass_rate": 0.8,
    "eval_1::overall_rating": 4,
    "eval_1::custom_depth": 2,
    "cost::mean_cost": 0.002,
    "cost::mean_total_llm_latency_ms": 1200,
    "cost::mean_total_tokens": 900,
  },
  rc_thorough: {
    "eval_1::pass_rate": 0.6,
    "eval_1::overall_rating": 5,
    "eval_1::custom_depth": 3,
    "cost::mean_cost": 0.006,
    "cost::mean_total_llm_latency_ms": 3000,
    "cost::mean_total_tokens": 2100,
  },
  rc_idle: {},
}

function lookup(values: ValueTable): RadarValueLookup {
  return (modelKey, dataKey) => {
    if (!modelKey) return null
    const value = values[modelKey]?.[dataKey]
    return value === undefined ? null : value
  }
}

const getValue = lookup(VALUES)

function chartData(overrides: {
  comparisonFeatures?: ComparisonFeature[]
  plottedConfigs?: TaskRunConfig[]
  selectedRunConfigIds?: string[]
  getValue?: RadarValueLookup
  scoreAxisMaxes?: Record<string, number>
  metricLabels?: Record<string, string>
  absoluteScale?: boolean
}) {
  return buildRadarChartData({
    comparisonFeatures: [EVAL_SECTION, USAGE_SECTION],
    plottedConfigs: [FAST, THOROUGH],
    selectedRunConfigIds: [FAST.id ?? "", THOROUGH.id ?? ""],
    getValue,
    modelInfo: null,
    scoreAxisMaxes: {},
    metricLabels: {},
    absoluteScale: false,
    ...overrides,
  })
}

describe("metricToScore", () => {
  it("lands every run config at the midpoint when they all tie", () => {
    expect(metricToScore(5, [5, 5, 5])).toBe(50)
  })

  it("lands a single run config at the midpoint", () => {
    expect(metricToScore(5, [5])).toBe(50)
  })

  it("scores the cheapest run config highest and the priciest lowest", () => {
    expect(metricToScore(1, [1, 100])).toBeCloseTo(90, 10)
    expect(metricToScore(100, [1, 100])).toBeCloseTo(10, 10)
  })

  it("compresses toward the midpoint when the spread is small next to the magnitude", () => {
    const tight = metricToScore(0.02, [0.02, 0.03])
    expect(tight).toBeGreaterThan(50)
    expect(tight).toBeLessThan(metricToScore(1, [1, 100]))
  })
})

describe("splitAxisKeys", () => {
  it("separates the usage section's rows from the eval score rows", () => {
    expect(splitAxisKeys([EVAL_SECTION, USAGE_SECTION])).toEqual({
      scoreKeys: [
        "eval_1::pass_rate",
        "eval_1::overall_rating",
        "eval_1::custom_depth",
      ],
      usageKeys: [
        "cost::mean_cost",
        "cost::mean_total_llm_latency_ms",
        "cost::mean_total_tokens",
      ],
    })
  })
})

describe("plottedRunConfigs", () => {
  it("leaves out a run config with no eval result at all", () => {
    const plotted = plottedRunConfigs({
      comparisonFeatures: [EVAL_SECTION, USAGE_SECTION],
      runConfigs: [FAST, THOROUGH, IDLE],
      selectedRunConfigIds: ["rc_fast", "rc_thorough", "rc_idle"],
      getValue,
    })
    expect(plotted.map((config) => config.id)).toEqual([
      "rc_fast",
      "rc_thorough",
    ])
  })

  it("keeps a run config with a single eval result", () => {
    const plotted = plottedRunConfigs({
      comparisonFeatures: [EVAL_SECTION, USAGE_SECTION],
      runConfigs: [IDLE],
      selectedRunConfigIds: ["rc_idle"],
      getValue: lookup({ rc_idle: { "eval_1::custom_depth": 1 } }),
    })
    expect(plotted.map((config) => config.id)).toEqual(["rc_idle"])
  })

  it("ignores a selected id that matches no run config", () => {
    const plotted = plottedRunConfigs({
      comparisonFeatures: [EVAL_SECTION, USAGE_SECTION],
      runConfigs: [FAST],
      selectedRunConfigIds: ["rc_gone", "rc_fast"],
      getValue,
    })
    expect(plotted).toEqual([FAST])
  })
})

describe("sharedAxisKeys", () => {
  it("keeps a key only when every plotted run config has a result for it", () => {
    const values = lookup({
      ...VALUES,
      rc_thorough: { ...VALUES.rc_thorough, "eval_1::custom_depth": null },
    })
    const { keys } = sharedAxisKeys(
      ["eval_1::pass_rate", "eval_1::custom_depth"],
      [FAST, THOROUGH],
      values,
    )
    expect(keys).toEqual(["eval_1::pass_rate"])
  })

  it("counts the keys it dropped", () => {
    const { omittedCount } = sharedAxisKeys(
      ["eval_1::pass_rate", "eval_1::unrun", "eval_1::also_unrun"],
      [FAST],
      getValue,
    )
    expect(omittedCount).toBe(2)
  })

  it("ignores a run config that is not being plotted", () => {
    const { keys, omittedCount } = sharedAxisKeys(
      ["eval_1::pass_rate", "eval_1::custom_depth"],
      [FAST],
      getValue,
    )
    expect(keys).toEqual(["eval_1::pass_rate", "eval_1::custom_depth"])
    expect(omittedCount).toBe(0)
  })
})

describe("axisMaxFor", () => {
  const relative = { absoluteScale: false, scoreAxisMaxes: {} }
  const fullScale = {
    absoluteScale: true,
    scoreAxisMaxes: {
      "eval_1::pass_rate": 1,
      "eval_1::overall_rating": 5,
    },
  }

  it("pads the highest value in the data by a tenth in relative mode", () => {
    expect(axisMaxFor("eval_1::pass_rate", 0.8, relative)).toBeCloseTo(0.88, 10)
    expect(axisMaxFor("eval_1::overall_rating", 5, relative)).toBeCloseTo(
      5.5,
      10,
    )
  })

  it("uses the score's own range in full scale mode", () => {
    expect(axisMaxFor("eval_1::pass_rate", 0.8, fullScale)).toBe(1)
    expect(axisMaxFor("eval_1::overall_rating", 4, fullScale)).toBe(5)
  })

  it("falls back to the normalized zero to one range when the score's range is unknown", () => {
    expect(axisMaxFor("eval_1::custom_depth", 0.4, fullScale)).toBe(1)
  })

  it("never returns a maximum below the data", () => {
    expect(axisMaxFor("eval_1::custom_depth", 3, fullScale)).toBeCloseTo(
      3.3,
      10,
    )
    expect(
      axisMaxFor("eval_1::overall_rating", 7, {
        ...fullScale,
        scoreAxisMaxes: { "eval_1::overall_rating": 5 },
      }),
    ).toBeCloseTo(7.7, 10)
  })

  it("gives an axis with no positive value a maximum of one", () => {
    expect(axisMaxFor("eval_1::custom_depth", 0, relative)).toBe(1)
  })
})

describe("buildAxisLabels", () => {
  it("uses the comparison table's own label for an eval score", () => {
    const labels = buildAxisLabels([EVAL_SECTION, USAGE_SECTION], {})
    expect(labels["eval_1::pass_rate"]).toBe("Pass Rate")
  })

  it("names a usage row for the direction that is better", () => {
    const labels = buildAxisLabels([EVAL_SECTION, USAGE_SECTION], {})
    expect(labels["cost::mean_cost"]).toBe("Cost Efficiency")
    expect(labels["cost::mean_total_llm_latency_ms"]).toBe("Speed")
  })

  it("prefers the name the user gave the row, over both the table and the usage name", () => {
    const labels = buildAxisLabels([EVAL_SECTION, USAGE_SECTION], {
      "eval_1::overall_rating": "Answer Quality",
      "cost::mean_total_llm_latency_ms": "Response Time",
    })
    expect(labels["eval_1::overall_rating"]).toBe("Answer Quality")
    expect(labels["cost::mean_total_llm_latency_ms"]).toBe("Response Time")
  })
})

describe("rankTooltipScores", () => {
  const manyKeys = Array.from(
    { length: 12 },
    (_, index) => `eval_1::score_${String(index + 1).padStart(2, "0")}`,
  )
  const manyLabels = Object.fromEntries(
    manyKeys.map((key, index) => [key, `Score ${index + 1}`]),
  )
  const manyMaxes = Object.fromEntries(manyKeys.map((key) => [key, 1]))

  it("keeps every score in axis order when there are ten or fewer", () => {
    const { scores, trimmedCount } = rankTooltipScores({
      keys: ["eval_1::overall_rating", "eval_1::pass_rate"],
      axisMaxes: { "eval_1::overall_rating": 5, "eval_1::pass_rate": 1 },
      axisLabels: {
        "eval_1::overall_rating": "Overall Rating",
        "eval_1::pass_rate": "Pass Rate",
      },
      getValue: (key) => getValue("rc_fast", key),
    })
    expect(scores).toEqual([
      { label: "Overall Rating", value: 4 },
      { label: "Pass Rate", value: 0.8 },
    ])
    expect(trimmedCount).toBe(0)
  })

  it("trims to the ten weakest and reports how many it dropped", () => {
    const { scores, trimmedCount } = rankTooltipScores({
      keys: manyKeys,
      axisMaxes: manyMaxes,
      axisLabels: manyLabels,
      getValue: (key) => 0.05 * (manyKeys.indexOf(key) + 1),
    })
    expect(trimmedCount).toBe(2)
    expect(scores.map((score) => score.label)).toEqual([
      "Score 1",
      "Score 2",
      "Score 3",
      "Score 4",
      "Score 5",
      "Score 6",
      "Score 7",
      "Score 8",
      "Score 9",
      "Score 10",
    ])
  })

  it("ranks by position on the axis rather than by raw value", () => {
    const { scores } = rankTooltipScores({
      keys: ["eval_1::overall_rating", "eval_1::pass_rate"],
      axisMaxes: { "eval_1::overall_rating": 5, "eval_1::pass_rate": 1 },
      axisLabels: {
        "eval_1::overall_rating": "Overall Rating",
        "eval_1::pass_rate": "Pass Rate",
      },
      getValue: (key) => (key === "eval_1::pass_rate" ? 0.9 : 1),
      limit: 1,
    })
    expect(scores).toEqual([{ label: "Overall Rating", value: 1 }])
  })

  it("sorts a score with no result first", () => {
    const { scores } = rankTooltipScores({
      keys: manyKeys,
      axisMaxes: manyMaxes,
      axisLabels: manyLabels,
      getValue: (key) =>
        key === "eval_1::score_12" ? null : 0.05 * (manyKeys.indexOf(key) + 1),
    })
    expect(scores[0]).toEqual({ label: "Score 12", value: null })
  })

  it("leaves the usage axes out", () => {
    const { scores } = rankTooltipScores({
      keys: ["eval_1::pass_rate", "cost::mean_cost"],
      axisMaxes: { "eval_1::pass_rate": 1, "cost::mean_cost": 100 },
      axisLabels: {
        "eval_1::pass_rate": "Pass Rate",
        "cost::mean_cost": "Cost Efficiency",
      },
      getValue: (key) => getValue("rc_fast", key),
    })
    expect(scores.map((score) => score.label)).toEqual(["Pass Rate"])
  })
})

describe("buildRadarChartData", () => {
  it("builds one axis per shared key and one series per plotted run config", () => {
    const data = chartData({})
    expect(data.indicators.map((indicator) => indicator.name)).toEqual([
      "Pass Rate",
      "Overall Rating",
      "Custom Depth",
      "Cost Efficiency",
      "Speed",
      "Token Efficiency",
    ])
    expect(data.legend).toEqual(["Fast Config", "Thorough Config"])
    expect(data.hasData).toBe(true)
    expect(data.omittedKeyCount).toBe(0)
  })

  it("scores the cheaper and faster run config higher on the usage axes", () => {
    const data = chartData({})
    const [fast, thorough] = data.series
    const costIndex = data.keys.indexOf("cost::mean_cost")
    const latencyIndex = data.keys.indexOf("cost::mean_total_llm_latency_ms")
    expect(fast.value[costIndex]).toBeGreaterThan(
      thorough.value[costIndex] as number,
    )
    expect(fast.value[latencyIndex]).toBeGreaterThan(
      thorough.value[latencyIndex] as number,
    )
  })

  it("puts every usage axis at the midpoint for a single run config", () => {
    const data = chartData({
      plottedConfigs: [FAST],
      selectedRunConfigIds: ["rc_fast"],
    })
    expect(data.keys.filter((key) => key.startsWith("cost::"))).toHaveLength(3)
    for (const key of data.keys.filter((k) => k.startsWith("cost::"))) {
      expect(data.series[0].value[data.keys.indexOf(key)]).toBe(50)
    }
  })

  it("has nothing to draw when no run config is selected, but still counts the axes the table could offer", () => {
    const data = chartData({ plottedConfigs: [], selectedRunConfigIds: [] })
    expect(data.hasData).toBe(false)
    expect(data.indicators).toEqual([])
    expect(data.series).toEqual([])
    expect(data.omittedKeyCount).toBe(0)
    expect(data.candidateAxisCount).toBe(6)
  })

  it("has nothing to draw when the plotted configs share fewer than three keys, and counts what it dropped", () => {
    const data = chartData({
      comparisonFeatures: [EVAL_SECTION],
      getValue: lookup({
        ...VALUES,
        rc_thorough: {
          "eval_1::pass_rate": 0.6,
          "eval_1::overall_rating": null,
          "eval_1::custom_depth": null,
        },
      }),
    })
    expect(data.hasData).toBe(false)
    expect(data.omittedKeyCount).toBe(2)
    expect(data.candidateAxisCount).toBe(3)
  })

  it("has nothing to draw when the table has no eval score rows", () => {
    const data = chartData({ comparisonFeatures: [USAGE_SECTION] })
    expect(data.hasData).toBe(false)
    expect(data.candidateAxisCount).toBe(3)
  })
})

describe("runConfigSeriesNames", () => {
  it("leaves a name that occurs once exactly as it is", () => {
    expect(runConfigSeriesNames([FAST, THOROUGH], null)).toEqual([
      "Fast Config",
      "Thorough Config",
    ])
  })

  it("numbers every occurrence of a name two run configs share", () => {
    const twin = make_config("rc_twin", "Fast Config")
    expect(runConfigSeriesNames([FAST, THOROUGH, twin], null)).toEqual([
      "Fast Config (1)",
      "Thorough Config",
      "Fast Config (2)",
    ])
  })
})
