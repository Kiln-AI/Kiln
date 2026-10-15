import { describe, expect, it } from "vitest"
import { buildCoverageModel, principlesFromTags } from "./coverage_model"

const P = [1, 2, 3, 4].map((n) => ({ n, text: `p${n}` }))

describe("principlesFromTags", () => {
  it("reads principle_<n> tags, sorted and de-duplicated", () => {
    expect(
      principlesFromTags([
        "eval_builder_v3",
        "principle_7",
        "principle_2",
        "principle_7",
      ]),
    ).toEqual([2, 7])
    expect(principlesFromTags(null)).toEqual([])
    expect(principlesFromTags(["principle_x"])).toEqual([])
  })
})

describe("buildCoverageModel", () => {
  it("splits each covered principle between its evals", () => {
    const m = buildCoverageModel(P, [
      { id: "a", principles: [1, 2] },
      { id: "b", principles: [2] },
    ])
    expect(m.shares.get(1)).toBeCloseTo(0.25)
    expect(m.evalWeights.get("a")).toBeCloseTo(0.25 + 0.125)
    expect(m.evalWeights.get("b")).toBeCloseTo(0.125)
    expect(m.covered).toBeCloseTo(0.5)
    expect(m.uncovered.map((p) => p.n)).toEqual([3, 4])
    expect(m.coverers.get(2)).toEqual(["a", "b"])
  })

  it("weights sum to the covered share", () => {
    const m = buildCoverageModel(P, [
      { id: "a", principles: [1, 2, 3] },
      { id: "b", principles: [3, 4] },
      { id: "c", principles: [4] },
    ])
    const sum = [...m.evalWeights.values()].reduce((s, v) => s + v, 0)
    expect(sum).toBeCloseTo(m.covered)
    expect(m.covered).toBeCloseTo(1)
  })

  it("gives an unmapped eval a small fixed weight", () => {
    const m = buildCoverageModel(P, [
      { id: "a", principles: [1] },
      { id: "u", principles: [] },
    ])
    expect(m.evalWeights.get("u")).toBeCloseTo(0.125)
    expect(m.covered).toBeCloseTo(0.25)
  })

  it("honours importance", () => {
    const m = buildCoverageModel(
      P,
      [{ id: "a", principles: [1] }],
      new Map([
        [1, 3],
        [2, 1],
        [3, 1],
        [4, 1],
      ]),
    )
    expect(m.shares.get(1)).toBeCloseTo(0.5)
    expect(m.covered).toBeCloseTo(0.5)
  })

  it("works without a constitution", () => {
    const m = buildCoverageModel(
      [],
      [
        { id: "a", principles: [] },
        { id: "b", principles: [] },
      ],
    )
    expect(m.evalWeights.get("a")).toBeCloseTo(0.5)
    expect(m.evalWeights.get("b")).toBeCloseTo(0.5)
    expect(m.covered).toBe(0)
    expect(m.uncovered).toEqual([])
  })
})
