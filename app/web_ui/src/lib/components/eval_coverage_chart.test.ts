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
        href: "/specs/p/t/builder?description=Principle%204",
        weight: 0.25,
        pass_rate: null,
        dataset_size: null,
        principles: [4],
        priority: null,
        status: null,
      },
    ],
    principles: [1, 2, 3, 4].map((n) => ({
      n,
      text: `Principle text ${n}`,
      group: n <= 2 ? "Careful" : "Honest",
    })),
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
    shares: new Map([
      [1, 0.25],
      [2, 0.25],
      [3, 0.25],
      [4, 0.25],
    ]),
    health: new Map<number, number | null>([
      [1, 0.74],
      [2, 0.74],
      [3, null],
      [4, null],
    ]),
    floor: null as CoverageData["floor"],
    active_count: 1,
    rulings: [],
    amendments: [],
    rulings_for: new Map(),
    constitution_version: null,
  }
}

function fixture_with_rulings(): CoverageData {
  const data = fixture()
  data.rulings = [
    {
      id: "C-1",
      date: "2026-09-01",
      status: "adopted",
      version: "v4",
      principles: [1],
      raised_by: "Sam",
      ruled_by: "Spencer",
      side: "UpKeep",
      question: "Does a delete need a yes?",
      ruling: "Yes.",
    },
    {
      id: "C-2",
      date: "2026-10-01",
      status: "open",
      principles: [],
      question: "Method?",
      ruling: "Pending.",
    },
  ]
  data.rulings_for = new Map([[1, ["C-1"]]])
  data.constitution_version = { version: "v11", date: "2026-10-21" }
  return data
}

function fixture_with_floor(): CoverageData {
  const data = fixture()
  data.floor = data.nodes[0]
  return data
}

afterEach(() => cleanup())

describe("EvalCoverageChart", () => {
  it("draws one circle per node, links evals, and one arc per principle", () => {
    const { container } = render(EvalCoverageChart, {
      data: fixture_with_floor(),
    })
    // 1 boundary + 3 nodes
    expect(container.querySelectorAll('svg[role="group"] circle')).toHaveLength(
      4,
    )
    const link = container.querySelector('svg a[href="/specs/p/t/s1"]')
    expect(link).not.toBeNull()
    // the gap links to the builder; the group labels sit on the ring
    expect(
      container.querySelector('svg a[href^="/specs/p/t/builder?description="]'),
    ).not.toBeNull()
    expect(container.querySelector('svg[role="group"]')?.textContent).toContain(
      "Careful",
    )
    expect(container.querySelector('svg[role="group"]')?.textContent).toContain(
      "Honest",
    )
    expect(container.querySelectorAll('svg g[role="button"]')).toHaveLength(4)
    expect(container.textContent).toContain("50%")
    expect(container.textContent).toContain("3 of 4")
    expect(container.textContent).toContain("Weakest eval")
  })

  it("shows the hovered eval and its principles in the panel", async () => {
    const { container } = render(EvalCoverageChart, { data: fixture() })
    const link = container.querySelector('svg a[href="/specs/p/t/s1"]')!
    await fireEvent.mouseEnter(link)
    expect(container.textContent).toContain("Pass rate")
    expect(container.textContent).toContain("74%")
    expect(container.textContent).toContain("Principles 1, 2")
    await fireEvent.mouseLeave(link)
    expect(container.textContent).toMatch(/Hover an arc/)
  })

  it("shows a principle and who covers it on arc hover", async () => {
    const { container } = render(EvalCoverageChart, { data: fixture() })
    const arcs = container.querySelectorAll('svg g[role="button"]')
    await fireEvent.mouseEnter(arcs[0])
    expect(container.textContent).toContain("Principle 1")
    expect(container.textContent).toContain("from Exact Record Modification")
    await fireEvent.mouseEnter(arcs[3])
    expect(container.textContent).toMatch(/no eval covers this principle/i)
  })

  it("draws the rulings ring and links a ruling to its principle and evals", async () => {
    const { container } = render(EvalCoverageChart, {
      data: fixture_with_rulings(),
    })
    // 4 arcs + 2 ruling dots
    expect(container.querySelectorAll('svg g[role="button"]')).toHaveLength(6)
    // one tick: C-1 on principle 1
    expect(container.querySelectorAll('svg[role="group"] line')).toHaveLength(1)
    expect(container.textContent).toContain("Rulings")
    expect(container.textContent).toContain("1 on a principle · 1 open")
    expect(container.textContent).toContain("v11, 2026-10-21")
    const dot = container.querySelector('svg g[aria-label^="C-1"]')!
    await fireEvent.mouseEnter(dot)
    expect(container.textContent).toContain("Does a delete need a yes?")
    expect(container.textContent).toContain("Spencer ruled")
    expect(container.textContent).toContain(
      "tested by Exact Record Modification",
    )
    // one hover line, from the dot to the arc
    expect(
      container.querySelectorAll('svg[role="group"] path[stroke-linecap]'),
    ).toHaveLength(1)
    await fireEvent.mouseLeave(dot)
    // the principle lists its rulings
    const arcs = container.querySelectorAll('svg g[role="button"]')
    await fireEvent.mouseEnter(arcs[0])
    expect(container.textContent).toContain("Rulings (1): C-1 (Sep 1)")
  })

  it("falls back to a count when there is no constitution", () => {
    const data = fixture()
    data.principles = []
    data.covered = null
    data.shares = new Map()
    data.health = new Map()
    data.nodes = data.nodes.filter((n) => n.kind === "eval")
    const { container } = render(EvalCoverageChart, { data })
    expect(container.textContent).toMatch(/sized by\s+priority/)
    expect(container.querySelectorAll('svg g[role="button"]')).toHaveLength(0)
  })
})
