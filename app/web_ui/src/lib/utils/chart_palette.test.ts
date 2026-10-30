import { describe, expect, it } from "vitest"
import { CHART_PALETTE } from "./chart_palette"

describe("CHART_PALETTE", () => {
  it("is the echarts 6 default palette, in order", () => {
    expect(CHART_PALETTE).toEqual([
      "#5070dd",
      "#b6d634",
      "#505372",
      "#ff994d",
      "#0ca8df",
      "#ffd10a",
      "#fb628b",
      "#785db0",
      "#3fbe95",
    ])
  })
})
