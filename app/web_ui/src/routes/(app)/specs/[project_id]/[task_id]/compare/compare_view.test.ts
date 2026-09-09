import { describe, it, expect } from "vitest"
import {
  applyMetricLabels,
  filterVisibleSections,
  listHiddenMetrics,
  parseHiddenListParam,
  parseMetricLabelsParam,
  withMetricLabel,
  type ComparisonSection,
} from "./compare_view"

const injection: ComparisonSection = {
  category: "Injection Attribution (Code)",
  eval_id: "eval_1",
  items: [
    {
      label: "Prompt Injection Correct",
      key: "eval_1::prompt_injection_correct",
    },
    { label: "Attack Missed", key: "eval_1::attack_missed" },
    { label: "Overall Correct", key: "eval_1::overall_correct" },
  ],
}

const tone: ComparisonSection = {
  category: "Tone",
  eval_id: "eval_2",
  items: [{ label: "Overall Correct", key: "eval_2::overall_correct" }],
}

const cost: ComparisonSection = {
  category: "Average Usage, Cost & Latency",
  eval_id: "kiln_cost_section",
  items: [
    { label: "Total Tokens", key: "cost::mean_total_tokens" },
    { label: "Cost (USD)", key: "cost::mean_cost" },
  ],
}

const sections = [injection, tone, cost]

describe("parseHiddenListParam", () => {
  it("returns nothing for a missing or empty param", () => {
    expect(parseHiddenListParam(null)).toEqual([])
    expect(parseHiddenListParam("")).toEqual([])
  })

  it("trims, dedupes and drops empty entries", () => {
    expect(parseHiddenListParam(" a, b ,,a,")).toEqual(["a", "b"])
  })

  it("drops entries the validator rejects", () => {
    expect(
      parseHiddenListParam(
        "eval_1::attack_missed,garbage,cost::mean_cost",
        (k) => k.includes("::"),
      ),
    ).toEqual(["eval_1::attack_missed", "cost::mean_cost"])
  })
})

describe("filterVisibleSections", () => {
  it("returns the same array when nothing is hidden", () => {
    expect(filterVisibleSections(sections, [], [])).toBe(sections)
  })

  it("drops hidden sections, the cost section included", () => {
    expect(
      filterVisibleSections(sections, ["eval_2", "kiln_cost_section"], []).map(
        (s) => s.eval_id,
      ),
    ).toEqual(["eval_1"])
  })

  it("drops hidden rows from any section", () => {
    const visible = filterVisibleSections(
      sections,
      [],
      ["eval_1::attack_missed", "cost::mean_cost"],
    )
    expect(visible.map((s) => s.items.map((i) => i.key))).toEqual([
      ["eval_1::prompt_injection_correct", "eval_1::overall_correct"],
      ["eval_2::overall_correct"],
      ["cost::mean_total_tokens"],
    ])
  })

  it("keeps a section whose rows are all hidden, with no items", () => {
    const visible = filterVisibleSections(
      sections,
      [],
      ["eval_2::overall_correct"],
    )
    const emptied = visible.find((s) => s.eval_id === "eval_2")
    expect(emptied).toBeDefined()
    expect(emptied?.items).toEqual([])
    expect(emptied?.category).toBe("Tone")
  })

  it("does not mutate the input", () => {
    filterVisibleSections(sections, ["eval_1"], ["eval_2::overall_correct"])
    expect(sections).toHaveLength(3)
    expect(tone.items).toHaveLength(1)
  })
})

describe("listHiddenMetrics", () => {
  it("returns nothing when no rows are hidden", () => {
    expect(listHiddenMetrics(sections, ["eval_1"], [])).toEqual([])
  })

  it("lists hidden rows in table order, each with its section name", () => {
    // Hidden in the reverse of table order, to show the order comes from the table
    const hidden = listHiddenMetrics(
      sections,
      [],
      ["cost::mean_cost", "eval_2::overall_correct", "eval_1::attack_missed"],
    )
    expect(hidden).toEqual([
      {
        key: "eval_1::attack_missed",
        label: "Attack Missed",
        section: "Injection Attribution (Code)",
      },
      {
        key: "eval_2::overall_correct",
        label: "Overall Correct",
        section: "Tone",
      },
      {
        key: "cost::mean_cost",
        label: "Cost (USD)",
        section: "Average Usage, Cost & Latency",
      },
    ])
  })

  it("leaves out rows of a hidden section", () => {
    const hidden = listHiddenMetrics(
      sections,
      ["eval_1"],
      ["eval_1::attack_missed", "eval_2::overall_correct"],
    )
    expect(hidden.map((h) => h.key)).toEqual(["eval_2::overall_correct"])
  })

  it("leaves out keys that match no row", () => {
    const hidden = listHiddenMetrics(
      sections,
      [],
      ["deleted_eval::score", "cost::mean_cost"],
    )
    expect(hidden.map((h) => h.key)).toEqual(["cost::mean_cost"])
  })
})

describe("parseMetricLabelsParam", () => {
  it("returns nothing for a missing param or one that is not a JSON object", () => {
    expect(parseMetricLabelsParam(null)).toEqual({})
    expect(parseMetricLabelsParam("")).toEqual({})
    expect(parseMetricLabelsParam("not json")).toEqual({})
    expect(parseMetricLabelsParam('["a"]')).toEqual({})
    expect(parseMetricLabelsParam("null")).toEqual({})
  })

  it("keeps trimmed string names for row keys and drops the rest", () => {
    const parsed = parseMetricLabelsParam(
      JSON.stringify({
        "eval_1::overall_correct": "  Injection OK ",
        "eval_2::overall_correct": "",
        "eval_3::overall_correct": 42,
        not_a_row_key: "Nope",
      }),
    )
    expect(parsed).toEqual({ "eval_1::overall_correct": "Injection OK" })
  })
})

describe("applyMetricLabels", () => {
  it("returns the same array when there are no labels", () => {
    expect(applyMetricLabels(sections, {})).toBe(sections)
  })

  it("relabels matching rows in any section and leaves the others alone", () => {
    const labeled = applyMetricLabels(sections, {
      "eval_1::overall_correct": "Injection OK",
      "cost::mean_cost": "Price",
      "unknown::key": "Ignored",
    })
    expect(labeled.map((s) => s.items.map((i) => i.label))).toEqual([
      ["Prompt Injection Correct", "Attack Missed", "Injection OK"],
      ["Overall Correct"],
      ["Total Tokens", "Price"],
    ])
  })

  it("does not mutate the input", () => {
    applyMetricLabels(sections, { "eval_2::overall_correct": "Tone OK" })
    expect(tone.items[0].label).toBe("Overall Correct")
  })
})

describe("withMetricLabel", () => {
  const key = "eval_1::overall_correct"

  it("stores a trimmed new name", () => {
    expect(
      withMetricLabel({}, key, "  Injection OK ", "Overall Correct"),
    ).toEqual({ [key]: "Injection OK" })
  })

  it("drops the override for an empty name or the original name", () => {
    const existing = { [key]: "Injection OK", other: "Kept" }
    expect(withMetricLabel(existing, key, "   ", "Overall Correct")).toEqual({
      other: "Kept",
    })
    expect(
      withMetricLabel(existing, key, "Overall Correct", "Overall Correct"),
    ).toEqual({ other: "Kept" })
  })

  it("does not mutate the input", () => {
    const existing = { [key]: "Injection OK" }
    withMetricLabel(existing, key, "", "Overall Correct")
    expect(existing).toEqual({ [key]: "Injection OK" })
  })
})
