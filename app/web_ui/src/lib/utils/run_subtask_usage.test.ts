import { afterEach, describe, it, expect, vi } from "vitest"
import type { TaskRun, Trace, TraceMessage } from "$lib/types"
import {
  calculate_subtask_usage,
  has_subtask_calls,
  known_subtask_usage,
  run_usage_totals,
  subtask_fetch_needs,
  usage_properties,
  type SubtaskReference,
  type SubtaskUsage,
} from "./run_subtask_usage"

afterEach(() => {
  vi.restoreAllMocks()
})

type Spend = { cost: number | null; total_tokens: number | null }

// A Kiln task tool message. `counted` is the usage newer runs record on it.
function subtask_call(
  run_id: string,
  counted?: Spend,
  tool_data = `project:::tool:::task:::${run_id}`,
): TraceMessage {
  return {
    role: "tool",
    tool_call_id: `call_${run_id}`,
    content: "subtask output",
    kiln_task_tool_data: tool_data,
    ...(counted ? { usage: counted } : {}),
  }
}

function saved_run(
  usage: (Spend & { total_llm_latency_ms: number }) | null,
  trace: Trace = [],
): TaskRun {
  return { usage, trace } as TaskRun
}

const COMPLETE = { latency_complete: true, cost_complete: true }

// Serves saved subtask runs by run id; anything else is a deleted run.
function fetcher(runs: Record<string, TaskRun>) {
  return vi.fn(async (reference: SubtaskReference) => {
    return runs[reference.run_id] ?? null
  })
}

describe("has_subtask_calls", () => {
  it("is true only when a message is a Kiln task tool call", () => {
    const plain_tool: TraceMessage = {
      role: "tool",
      tool_call_id: "c1",
      content: "4",
    }
    expect(has_subtask_calls(null)).toBe(false)
    expect(has_subtask_calls([plain_tool])).toBe(false)
    expect(has_subtask_calls([plain_tool, subtask_call("r1")])).toBe(true)
  })
})

describe("calculate_subtask_usage", () => {
  it("reports a counted subtask without adding it to the run's total again", async () => {
    const fetch_run = fetcher({
      r1: saved_run({
        cost: 0.01,
        total_tokens: 1050,
        total_llm_latency_ms: 700,
      }),
    })

    const usage = await calculate_subtask_usage(
      [subtask_call("r1", { cost: 0.01, total_tokens: 1050 })],
      fetch_run,
    )

    expect(usage).toEqual({
      cost: 0.01,
      tokens: 1050,
      latency_ms: 700,
      uncounted_cost: 0,
      uncounted_tokens: 0,
      ...COMPLETE,
    })
  })

  it("reads a counted subtask from the trace when its run was never saved", async () => {
    const fetch_run = fetcher({})

    const usage = await calculate_subtask_usage(
      [subtask_call("None", { cost: 0.01, total_tokens: 1050 })],
      fetch_run,
    )

    expect(fetch_run).not.toHaveBeenCalled()
    expect(usage).toMatchObject({
      cost: 0.01,
      tokens: 1050,
      uncounted_cost: 0,
      cost_complete: true,
      latency_complete: false,
    })
  })

  it("counts a nested counted subtask once", async () => {
    // r1's recorded usage already holds its own subtask r2.
    const fetch_run = fetcher({
      r1: saved_run(
        { cost: 0.13, total_tokens: 13000, total_llm_latency_ms: 300 },
        [subtask_call("r2", { cost: 0.1, total_tokens: 10000 })],
      ),
      r2: saved_run({
        cost: 0.1,
        total_tokens: 10000,
        total_llm_latency_ms: 500,
      }),
    })

    const usage = await calculate_subtask_usage(
      [subtask_call("r1", { cost: 0.13, total_tokens: 13000 })],
      fetch_run,
    )

    expect(usage).toEqual({
      cost: 0.13,
      tokens: 13000,
      latency_ms: 800,
      uncounted_cost: 0,
      uncounted_tokens: 0,
      ...COMPLETE,
    })
  })

  it("adds subtasks of an older run, nested ones included, as uncounted", async () => {
    const fetch_run = fetcher({
      r1: saved_run(
        { cost: 0.03, total_tokens: 3000, total_llm_latency_ms: 300 },
        [subtask_call("r2")],
      ),
      r2: saved_run({
        cost: 0.1,
        total_tokens: 10000,
        total_llm_latency_ms: 500,
      }),
    })

    const usage = await calculate_subtask_usage([subtask_call("r1")], fetch_run)

    expect(usage.cost).toBeCloseTo(0.13)
    expect(usage.uncounted_cost).toBeCloseTo(0.13)
    expect(usage).toMatchObject({
      tokens: 13000,
      uncounted_tokens: 13000,
      latency_ms: 800,
    })
  })

  it("skips an older subtask whose run was deleted", async () => {
    const fetch_run = fetcher({
      kept: saved_run({
        cost: 0.02,
        total_tokens: 20,
        total_llm_latency_ms: 5,
      }),
    })

    const usage = await calculate_subtask_usage(
      [subtask_call("deleted"), subtask_call("kept")],
      fetch_run,
    )

    expect(fetch_run).toHaveBeenCalledTimes(2)
    expect(usage).toMatchObject({
      cost: 0.02,
      uncounted_cost: 0.02,
      tokens: 20,
      cost_complete: false,
      latency_complete: false,
    })
  })

  it("skips and logs an older subtask whose fetch fails", async () => {
    const fetch_run = vi.fn(async (reference: SubtaskReference) => {
      if (reference.run_id === "broken") throw new Error("network down")
      return saved_run({
        cost: 0.02,
        total_tokens: 20,
        total_llm_latency_ms: 5,
      })
    })
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    const usage = await calculate_subtask_usage(
      [subtask_call("broken"), subtask_call("kept")],
      fetch_run,
    )

    expect(warn).toHaveBeenCalledTimes(1)
    expect(usage).toMatchObject({
      cost: 0.02,
      uncounted_cost: 0.02,
      tokens: 20,
    })
  })

  it("adds only the uncounted subtask when counted and older calls are mixed", async () => {
    // A conversation whose first turn was saved before tool messages carried usage.
    const fetch_run = fetcher({
      old: saved_run({
        cost: 0.02,
        total_tokens: 200,
        total_llm_latency_ms: 50,
      }),
      new: saved_run({
        cost: 0.01,
        total_tokens: 100,
        total_llm_latency_ms: 70,
      }),
    })

    const usage = await calculate_subtask_usage(
      [
        subtask_call("old"),
        subtask_call("new", { cost: 0.01, total_tokens: 100 }),
      ],
      fetch_run,
    )

    expect(usage.cost).toBeCloseTo(0.03)
    expect(usage.uncounted_cost).toBeCloseTo(0.02)
    expect(usage).toMatchObject({
      tokens: 300,
      uncounted_tokens: 200,
      latency_ms: 120,
    })
  })

  it("flags an older unsaved subtask as unknown, without a fetch", async () => {
    const fetch_run = fetcher({})

    const usage = await calculate_subtask_usage(
      [subtask_call("None")],
      fetch_run,
    )

    expect(fetch_run).not.toHaveBeenCalled()
    expect(usage).toEqual({
      cost: 0,
      tokens: 0,
      latency_ms: 0,
      uncounted_cost: 0,
      uncounted_tokens: 0,
      latency_complete: false,
      cost_complete: false,
    })
  })

  it("counts a subtask run referenced twice once", async () => {
    const fetch_run = fetcher({
      r1: saved_run({
        cost: 0.01,
        total_tokens: 100,
        total_llm_latency_ms: 70,
      }),
      r2: saved_run({
        cost: 0.02,
        total_tokens: 200,
        total_llm_latency_ms: 50,
      }),
    })
    const counted = { cost: 0.01, total_tokens: 100 }

    const usage = await calculate_subtask_usage(
      [
        subtask_call("r1", counted),
        subtask_call("r1", counted),
        subtask_call("r2"),
        subtask_call("r2"),
      ],
      fetch_run,
    )

    expect(fetch_run).toHaveBeenCalledTimes(2)
    expect(usage.cost).toBeCloseTo(0.03)
    expect(usage.uncounted_cost).toBeCloseTo(0.02)
    expect(usage).toMatchObject({ tokens: 300, latency_ms: 120 })
    expect(
      known_subtask_usage([
        subtask_call("r1", counted),
        subtask_call("r1", counted),
      ]).cost,
    ).toBeCloseTo(0.01)
  })

  it("treats a null cost or token count on a tool message as zero", async () => {
    const usage = await calculate_subtask_usage(
      [
        subtask_call("None", { cost: null, total_tokens: 100 }),
        subtask_call("None", { cost: 0.01, total_tokens: null }),
      ],
      fetcher({}),
    )

    expect(usage).toMatchObject({
      cost: 0.01,
      tokens: 100,
      cost_complete: true,
    })
  })

  it("adds nothing for an older saved subtask run with no usage", async () => {
    const usage = await calculate_subtask_usage(
      [subtask_call("r1")],
      fetcher({ r1: saved_run(null) }),
    )

    expect(usage).toMatchObject({
      cost: 0,
      tokens: 0,
      latency_ms: 0,
      ...COMPLETE,
    })
  })

  it("keeps the counted usage of a call with malformed tool data", async () => {
    const fetch_run = fetcher({})

    const usage = await calculate_subtask_usage(
      [subtask_call("x", { cost: 0.01, total_tokens: 100 }, "not:::enough")],
      fetch_run,
    )

    expect(fetch_run).not.toHaveBeenCalled()
    expect(usage).toMatchObject({
      cost: 0.01,
      tokens: 100,
      cost_complete: true,
      latency_complete: false,
    })
  })
})

describe("run_usage_totals", () => {
  const run_usage = { cost: 0.013, tokens: 1220, latency_ms: 400 }

  function subtasks(overrides: Partial<SubtaskUsage>): SubtaskUsage {
    return {
      cost: 0,
      tokens: 0,
      latency_ms: 0,
      uncounted_cost: 0,
      uncounted_tokens: 0,
      ...COMPLETE,
      ...overrides,
    }
  }

  it("keeps the run's cost when its usage already holds the subtasks", () => {
    const totals = run_usage_totals(
      run_usage,
      subtasks({ cost: 0.01, tokens: 1050, latency_ms: 300 }),
    )

    expect(totals).toEqual({ cost: 0.013, tokens: 1220, latency_ms: 700 })
  })

  it("adds the subtasks an older run's usage does not hold", () => {
    const totals = run_usage_totals(
      run_usage,
      subtasks({
        cost: 0.01,
        tokens: 1050,
        latency_ms: 300,
        uncounted_cost: 0.01,
        uncounted_tokens: 1050,
      }),
    )

    expect(totals.cost).toBeCloseTo(0.023)
    expect(totals).toMatchObject({ tokens: 2270, latency_ms: 700 })
  })

  it("is the run's own usage when there are no subtasks", () => {
    expect(run_usage_totals(run_usage, null)).toEqual(run_usage)
  })
})

describe("known_subtask_usage and subtask_fetch_needs", () => {
  it("reads counted figures from the trace and names the rows that need a fetch", () => {
    const trace = [
      subtask_call("saved", { cost: 0.01, total_tokens: 100 }),
      subtask_call("None", { cost: 0.02, total_tokens: 200 }),
    ]

    expect(known_subtask_usage(trace)).toMatchObject({
      cost: 0.03,
      tokens: 300,
      cost_complete: true,
      latency_complete: false,
    })
    expect(subtask_fetch_needs(trace)).toEqual({ cost: false, latency: true })
  })

  it("needs a fetch for cost only when an older call has a saved run", () => {
    expect(subtask_fetch_needs([subtask_call("old")])).toEqual({
      cost: true,
      latency: true,
    })
    expect(subtask_fetch_needs([subtask_call("None")])).toEqual({
      cost: false,
      latency: false,
    })
  })
})

describe("usage_properties", () => {
  const run_usage = { cost: 0.013, tokens: 1220, latency_ms: 400 }
  const eval_run_subtasks: SubtaskUsage = {
    cost: 0.01,
    tokens: 1050,
    latency_ms: 0,
    uncounted_cost: 0,
    uncounted_tokens: 0,
    cost_complete: true,
    latency_complete: false,
  }

  it("shows known cost while only latency loads", () => {
    const rows = usage_properties(run_usage, eval_run_subtasks, {
      cost: false,
      latency: true,
    })

    expect(rows.map((row) => [row.name, row.value])).toEqual([
      ["Total Cost", "$0.013000"],
      ["Subtasks Cost", "$0.010000"],
      ["Total Tokens", 1220],
      ["Subtasks Tokens", 1050],
      ["Total Latency", "Loading..."],
      ["Subtasks Latency", "Loading..."],
    ])
  })

  it("marks a latency total that leaves out subtasks", () => {
    const rows = usage_properties(run_usage, eval_run_subtasks, {
      cost: false,
      latency: false,
    })

    const latency = rows.find((row) => row.name === "Total Latency")
    expect(latency?.warn_icon).toBe(true)
    expect(latency?.tooltip).toContain("eval run")
    const cost = rows.find((row) => row.name === "Total Cost")
    expect(cost?.warn_icon).toBeUndefined()
  })

  it("marks a cost total that leaves out an older subtask", () => {
    const rows = usage_properties(
      run_usage,
      { ...eval_run_subtasks, cost: 0, tokens: 0, cost_complete: false },
      { cost: false, latency: false },
    )

    expect(rows.find((row) => row.name === "Total Cost")?.warn_icon).toBe(true)
    expect(rows.find((row) => row.name === "Total Tokens")?.warn_icon).toBe(
      true,
    )
  })

  it("shows the run's own figures with no warning when there are no subtasks", () => {
    const rows = usage_properties(run_usage, null, {
      cost: false,
      latency: false,
    })

    expect(rows.map((row) => row.name)).toEqual([
      "Total Cost",
      "Total Tokens",
      "Total Latency",
    ])
    expect(rows.some((row) => row.warn_icon)).toBe(false)
  })
})
