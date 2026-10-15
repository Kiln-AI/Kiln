// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import EvalCoverageChart from "./eval_coverage_chart.svelte"
import type { CoverageData } from "$lib/utils/eval_coverage/eval_coverage_data"

function fixture(): CoverageData {
  return {
    nodes: [
      {
        id: "s1",
        name: "Exact Record Modification",
        kind: "eval",
        href: "/specs/p/t/s1",
        weight: 0.5,
        pass_rate: 0.74,
        dataset_size: 39,
        principles: [1, 2],
        priority: 1,
        status: "active",
      },
      {
        id: "s2",
        name: "Language Check",
        kind: "planned",
        href: "/specs/p/t/s2",
        weight: 0.25,
        pass_rate: null,
        dataset_size: null,
        principles: [3],
        priority: 2,
        status: "future",
      },
      {
        id: "gap-4",
        name: "Which reply speaks the user's language?",
        kind: "gap",
        href: null,
        weight: 0.25,
        pass_rate: null,
        dataset_size: null,
        principles: [4],
        priority: null,
        status: null,
      },
    ],
    principles: [1, 2, 3, 4].map((n) => ({ n, text: `Principle text ${n}` })),
    covered: 0.5,
    coverers: new Map([
      [1, ["s1"]],
      [2, ["s1"]],
      [3, []],
      [4, []],
    ]),
    planned_for: new Map([
      [3, ["s2"]],
      [4, []],
    ]),
    active_count: 1,
  }
}

afterEach(() => cleanup())

describe("EvalCoverageChart", () => {
  it("draws one circle per node, links evals, and one arc per principle", () => {
    const { container } = render(EvalCoverageChart, { data: fixture() })
    // 1 boundary + 3 nodes
    expect(container.querySelectorAll("svg circle")).toHaveLength(4)
    const link = container.querySelector('svg a[href="/specs/p/t/s1"]')
    expect(link).not.toBeNull()
    expect(container.querySelectorAll('svg g[role="button"]')).toHaveLength(4)
    expect(container.textContent).toContain("50%")
    expect(container.textContent).toContain("3 of 4")
  })

  it("shows the hovered eval and its principles in the panel", async () => {
    const { container } = render(EvalCoverageChart, { data: fixture() })
    const link = container.querySelector('svg a[href="/specs/p/t/s1"]')!
    await fireEvent.mouseEnter(link)
    expect(container.textContent).toContain("Pass rate")
    expect(container.textContent).toContain("74%")
    expect(container.textContent).toContain("Principles 1, 2")
    await fireEvent.mouseLeave(link)
    expect(container.textContent).toContain("Hover a circle")
  })

  it("shows a principle and who covers it on arc hover", async () => {
    const { container } = render(EvalCoverageChart, { data: fixture() })
    const arcs = container.querySelectorAll('svg g[role="button"]')
    await fireEvent.mouseEnter(arcs[0])
    expect(container.textContent).toContain("Principle 1")
    expect(container.textContent).toContain(
      "Covered by Exact Record Modification",
    )
    await fireEvent.mouseEnter(arcs[3])
    expect(container.textContent).toContain("No eval covers this principle")
  })

  it("falls back to a count when there is no constitution", () => {
    const data = fixture()
    data.principles = []
    data.covered = null
    data.nodes = data.nodes.filter((n) => n.kind === "eval")
    const { container } = render(EvalCoverageChart, { data })
    expect(container.textContent).toMatch(/sized by\s+priority/)
    expect(container.querySelectorAll('svg g[role="button"]')).toHaveLength(0)
  })
})
