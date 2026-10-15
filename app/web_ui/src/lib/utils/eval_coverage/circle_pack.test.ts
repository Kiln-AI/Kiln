import { describe, expect, it } from "vitest"
import {
  circleIntersections,
  packInCircle,
  packWeighted,
  packingDensity,
  recentre,
  type PackedCircle,
} from "./circle_pack"

function assertValid(placed: PackedCircle[], R: number) {
  for (const c of placed) {
    expect(Math.hypot(c.x, c.y) + c.r).toBeLessThanOrEqual(R + 1e-3)
  }
  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i]
      const b = placed[j]
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(
        a.r + b.r - 1e-3,
      )
    }
  }
}

describe("circleIntersections", () => {
  it("finds two points for overlapping circles", () => {
    const pts = circleIntersections(0, 0, 1, 1, 0, 1)
    expect(pts).toHaveLength(2)
    for (const p of pts) {
      expect(p.x).toBeCloseTo(0.5)
      expect(Math.abs(p.y)).toBeCloseTo(Math.sqrt(3) / 2)
    }
  })

  it("returns one point for tangent circles", () => {
    expect(circleIntersections(0, 0, 1, 2, 0, 1)).toHaveLength(1)
  })

  it("returns nothing for separate or concentric circles", () => {
    expect(circleIntersections(0, 0, 1, 5, 0, 1)).toHaveLength(0)
    expect(circleIntersections(0, 0, 1, 0, 0, 2)).toHaveLength(0)
  })
})

describe("packInCircle", () => {
  it("puts a single circle at the centre", () => {
    const { placed, unplaced } = packInCircle([{ id: "a", r: 2 }], 10)
    expect(unplaced).toHaveLength(0)
    expect(placed[0]).toMatchObject({ id: "a", x: 0, y: 0, r: 2 })
  })

  it("places two equal circles tangent to each other", () => {
    const { placed } = packInCircle(
      [
        { id: "a", r: 3 },
        { id: "b", r: 3 },
      ],
      10,
    )
    expect(placed).toHaveLength(2)
    const [a, b] = placed
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(6, 3)
    assertValid(placed, 10)
  })

  it("packs big and small circles without overlap, inside the boundary", () => {
    const items = [
      ...[1, 2, 3, 4].map((i) => ({ id: `big${i}`, r: 30 })),
      ...Array.from({ length: 12 }, (_, i) => ({ id: `small${i}`, r: 6 })),
    ]
    const { placed, unplaced } = packInCircle(items, 100)
    expect(unplaced).toHaveLength(0)
    expect(placed).toHaveLength(16)
    assertValid(placed, 100)
  })

  it("is deterministic and independent of input order", () => {
    const items = Array.from({ length: 10 }, (_, i) => ({
      id: `c${i}`,
      r: 5 + (i % 4) * 4,
    }))
    const a = packInCircle(items, 60).placed
    const b = packInCircle([...items].reverse(), 60).placed
    expect(a).toEqual(b)
  })

  it("reports circles that do not fit", () => {
    const { placed, unplaced } = packInCircle(
      [
        { id: "huge", r: 9 },
        { id: "other", r: 9 },
      ],
      10,
    )
    expect(placed).toHaveLength(1)
    expect(unplaced.map((u) => u.id)).toEqual(["other"])
  })

  it("places lower passes first and keeps fixed circles in place", () => {
    const first = packInCircle([{ id: "fixed", r: 5 }], 20).placed
    const { placed } = packInCircle(
      [
        { id: "ghost", r: 4, pass: 1 },
        { id: "real", r: 3, pass: 0 },
      ],
      20,
      first,
    )
    expect(placed.map((p) => p.id)).toEqual(["real", "ghost"])
    assertValid([...first, ...placed], 20)
  })
})

describe("packWeighted", () => {
  it("sizes circles by area and fills the requested share", () => {
    const items = [
      { id: "a", weight: 4 },
      { id: "b", weight: 1 },
    ]
    const { placed, scale } = packWeighted(items, 100, 0.5)
    const a = placed.find((p) => p.id === "a")!
    const b = placed.find((p) => p.id === "b")!
    expect(a.r / b.r).toBeCloseTo(2, 5)
    expect(scale).toBeGreaterThan(0)
    expect(packingDensity(placed, 100)).toBeCloseTo(0.5, 5)
  })

  it("shrinks the scale until everything fits", () => {
    const items = Array.from({ length: 4 }, (_, i) => ({
      id: `p${i}`,
      weight: 1,
    }))
    const { placed, unplaced } = packWeighted(items, 100, 0.95)
    expect(unplaced).toHaveLength(0)
    expect(placed).toHaveLength(4)
    assertValid(placed, 100)
    expect(packingDensity(placed, 100)).toBeLessThan(0.95)
  })

  it("drops items with no weight", () => {
    const { placed, unplaced } = packWeighted(
      [
        { id: "a", weight: 1 },
        { id: "z", weight: 0 },
      ],
      10,
      0.5,
    )
    expect(placed.map((p) => p.id)).toEqual(["a"])
    expect(unplaced.map((p) => p.id)).toEqual(["z"])
  })
})

describe("recentre", () => {
  it("balances a one-sided cluster and keeps it inside the boundary", () => {
    const placed = [
      { id: "a", r: 10, x: 30, y: 0 },
      { id: "b", r: 10, x: 50, y: 0 },
    ]
    const out = recentre(placed, 100)
    const mid = (out[0].x + out[1].x) / 2
    expect(Math.abs(mid)).toBeLessThan(0.5)
    expect(Math.abs(out[0].y)).toBeLessThan(0.5)
    assertValid(out, 100)
  })

  it("leaves a cluster alone when centring would not fit", () => {
    const placed = [{ id: "a", r: 95, x: 0, y: 0 }]
    expect(recentre(placed, 100)).toEqual(placed)
  })
})
