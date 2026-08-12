import { describe, it, expect } from "vitest"
import { capped_rank_scores, describe_rank, type RankInput } from "./rank_score"

function scores(
  values: RankInput[],
  better: "higher" | "lower" = "lower",
): Record<string, number | null> {
  return Object.fromEntries(capped_rank_scores(values, better))
}

describe("capped_rank_scores", () => {
  it("orders lower-is-better metrics with the cheapest highest", () => {
    expect(
      scores(
        [
          { id: "a", value: 0.4 },
          { id: "b", value: 0.1 },
          { id: "c", value: 0.2 },
        ],
        "lower",
      ),
    ).toEqual({
      b: 5 / 6,
      c: 0.5,
      a: 1 / 6,
    })
  })

  it("inverts for a higher-is-better metric", () => {
    const values: RankInput[] = [
      { id: "a", value: 0.4 },
      { id: "b", value: 0.1 },
      { id: "c", value: 0.2 },
    ]
    const lower = scores(values, "lower")
    const higher = scores(values, "higher")
    // Same three scores, handed to the opposite ends
    expect(higher).toEqual({ a: 5 / 6, c: 0.5, b: 1 / 6 })
    expect(Object.values(lower).sort()).toEqual(Object.values(higher).sort())
  })

  it("scores a single config 0.5 - one config has no rank", () => {
    expect(scores([{ id: "only", value: 12 }])).toEqual({ only: 0.5 })
  })

  it("scores a pair 0.75 / 0.25, whatever the gap between them", () => {
    expect(
      scores([
        { id: "cheap", value: 0.01 },
        { id: "dear", value: 0.02 },
      ]),
    ).toEqual({ cheap: 0.75, dear: 0.25 })
    // A thousand-fold gap draws exactly the same two heights: the axis says
    // which won, and nothing about by how much.
    expect(
      scores([
        { id: "cheap", value: 0.01 },
        { id: "dear", value: 10 },
      ]),
    ).toEqual({ cheap: 0.75, dear: 0.25 })
  })

  it("is bounded strictly inside (0,1) - it never reaches either end", () => {
    for (const n of [1, 2, 3, 5, 12, 50]) {
      const values = Array.from({ length: n }, (_unused, index) => ({
        id: `c${index}`,
        value: index,
      }))
      const result = [...capped_rank_scores(values, "lower").values()]
      expect(result).toHaveLength(n)
      for (const score of result) {
        expect(score).not.toBeNull()
        expect(score as number).toBeGreaterThan(0)
        expect(score as number).toBeLessThan(1)
      }
      // The caps themselves: best is 1 - 0.5/n, worst is 0.5/n
      expect(Math.max(...(result as number[]))).toBeCloseTo(1 - 0.5 / n, 12)
      expect(Math.min(...(result as number[]))).toBeCloseTo(0.5 / n, 12)
    }
  })

  it("gives tied configs the same score, from the average of their places", () => {
    // Two tied for first out of four: midrank 1.5 for both, then 3 and 4.
    expect(
      scores([
        { id: "a", value: 1 },
        { id: "b", value: 1 },
        { id: "c", value: 2 },
        { id: "d", value: 3 },
      ]),
    ).toEqual({
      a: (4 - 1.5 + 0.5) / 4,
      b: (4 - 1.5 + 0.5) / 4,
      c: (4 - 3 + 0.5) / 4,
      d: (4 - 4 + 0.5) / 4,
    })
  })

  it("collapses an all-tied axis onto one height", () => {
    const result = scores([
      { id: "a", value: 7 },
      { id: "b", value: 7 },
      { id: "c", value: 7 },
    ])
    expect(result).toEqual({ a: 0.5, b: 0.5, c: 0.5 })
  })

  it("does not let input order change any score", () => {
    const values: RankInput[] = [
      { id: "a", value: 3 },
      { id: "b", value: 1 },
      { id: "c", value: 1 },
      { id: "d", value: 9 },
    ]
    const forward = scores(values)
    const backward = scores([...values].reverse())
    expect(backward).toEqual(forward)
  })

  it("maps an unmeasured config to null, never to zero", () => {
    const result = scores([
      { id: "a", value: 0.1 },
      { id: "missing", value: null },
      { id: "b", value: 0.2 },
    ])
    expect(result.missing).toBeNull()
    // ...and it is out of the denominator: the two measured configs are a pair
    expect(result).toEqual({ a: 0.75, missing: null, b: 0.25 })
  })

  it("treats a non-finite value as unmeasured", () => {
    const result = scores([
      { id: "a", value: 1 },
      { id: "nan", value: Number.NaN },
      { id: "inf", value: Number.POSITIVE_INFINITY },
    ])
    expect(result).toEqual({ a: 0.5, nan: null, inf: null })
  })

  it("returns a null for every id when nothing was measured", () => {
    expect(
      scores([
        { id: "a", value: null },
        { id: "b", value: null },
      ]),
    ).toEqual({ a: null, b: null })
  })

  it("returns an empty map for an empty comparison", () => {
    expect(capped_rank_scores([], "lower").size).toBe(0)
  })

  it("is outlier-robust: a 27x cost moves the axis by one step, not to the floor", () => {
    const mild: RankInput[] = [
      { id: "a", value: 0.1 },
      { id: "b", value: 0.2 },
      { id: "c", value: 0.3 },
      { id: "glm", value: 0.4 },
    ]
    const outlier: RankInput[] = [
      { id: "a", value: 0.1 },
      { id: "b", value: 0.2 },
      { id: "c", value: 0.3 },
      // The real case this exists for: the GLM lane invoiced ~27x the mini
      // lanes on the same corpus.
      { id: "glm", value: 0.1 * 27 },
    ]
    // Every score is identical - the outlier is still last, and the three
    // configs behind it keep the spacing they had. Min-max would have pinned
    // a, b and c to 0.00, 0.04 and 0.08 instead.
    expect(scores(outlier)).toEqual(scores(mild))
    expect(scores(outlier)).toEqual({
      a: 7 / 8,
      b: 5 / 8,
      c: 3 / 8,
      glm: 1 / 8,
    })
  })

  it("re-ranks when a config leaves the comparison - the scale is the selection", () => {
    const all: RankInput[] = [
      { id: "a", value: 1 },
      { id: "b", value: 2 },
      { id: "c", value: 3 },
    ]
    expect(scores(all).b).toBeCloseTo(0.5, 12)
    // Hide the cheapest and b is now the expensive half of a pair
    expect(scores(all.filter((entry) => entry.id !== "a")).b).toBeCloseTo(
      0.75,
      12,
    )
  })

  it("keeps every score a mean of 0.5 across the axis", () => {
    // Sum of (n - rank + 0.5)/n over all ranks is n/2 for any n, tied or not -
    // the property that makes one axis's scores comparable to another's.
    for (const values of [
      [1, 2, 3, 4, 5],
      [1, 1, 1, 4, 9],
      [2, 2, 3, 3],
    ]) {
      const result = [
        ...capped_rank_scores(
          values.map((value, index) => ({ id: `c${index}`, value })),
          "lower",
        ).values(),
      ] as number[]
      const mean = result.reduce((sum, score) => sum + score, 0) / result.length
      expect(mean).toBeCloseTo(0.5, 12)
    }
  })
})

describe("describe_rank", () => {
  it("reads a score back as the place it stands for", () => {
    const result = capped_rank_scores(
      [
        { id: "a", value: 5 },
        { id: "b", value: 1 },
        { id: "c", value: 3 },
        { id: "d", value: 4 },
        { id: "e", value: 2 },
      ],
      "lower",
    )
    expect(describe_rank(result.get("b") ?? null, 5)).toBe("1st of 5")
    expect(describe_rank(result.get("e") ?? null, 5)).toBe("2nd of 5")
    expect(describe_rank(result.get("c") ?? null, 5)).toBe("3rd of 5")
    expect(describe_rank(result.get("d") ?? null, 5)).toBe("4th of 5")
    expect(describe_rank(result.get("a") ?? null, 5)).toBe("5th of 5")
  })

  it("names a tie as one", () => {
    const result = capped_rank_scores(
      [
        { id: "a", value: 1 },
        { id: "b", value: 1 },
        { id: "c", value: 2 },
        { id: "d", value: 3 },
      ],
      "lower",
    )
    expect(describe_rank(result.get("a") ?? null, 4)).toBe("tied 1st–2nd of 4")
    expect(describe_rank(result.get("b") ?? null, 4)).toBe("tied 1st–2nd of 4")
    expect(describe_rank(result.get("c") ?? null, 4)).toBe("3rd of 4")
  })

  it("handles the ordinal exceptions", () => {
    // 11th-13th are "th" whatever their last digit says
    for (const [rank, text] of [
      [1, "1st"],
      [2, "2nd"],
      [3, "3rd"],
      [4, "4th"],
      [11, "11th"],
      [12, "12th"],
      [13, "13th"],
      [21, "21st"],
      [22, "22nd"],
      [23, "23rd"],
    ] as [number, string][]) {
      const n = 25
      expect(describe_rank((n - rank + 0.5) / n, n)).toBe(`${text} of ${n}`)
    }
  })

  it("says nothing when there is nothing to say", () => {
    expect(describe_rank(null, 5)).toBeNull()
    expect(describe_rank(0.5, 0)).toBeNull()
    expect(describe_rank(Number.NaN, 5)).toBeNull()
    // A score paired with the wrong comparison size resolves to a rank that
    // size could not produce, and is left unsaid rather than printed
    expect(describe_rank(0.99, 3)).toBeNull()
    expect(describe_rank(0.01, 3)).toBeNull()
  })

  it("round-trips every rank for every comparison size it can be drawn at", () => {
    for (let n = 1; n <= 12; n += 1) {
      for (let rank = 1; rank <= n; rank += 1) {
        expect(describe_rank((n - rank + 0.5) / n, n)).toContain(`of ${n}`)
      }
    }
  })
})
