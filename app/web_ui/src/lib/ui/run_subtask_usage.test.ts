import { describe, it, expect, vi } from "vitest"
import type { TaskRun, Trace, TraceMessage } from "$lib/types"
import {
  calculate_subtask_usage,
  has_subtask_calls,
  type SubtaskReference,
} from "./run_subtask_usage"

type Spend = { cost: number; total_tokens: number }

// A Kiln task tool message. `counted` is the usage newer runs record on it.
function subtask_call(run_id: string, counted?: Spend): TraceMessage {
  return {
    role: "tool",
    tool_call_id: `call_${run_id}`,
    content: "subtask output",
    kiln_task_tool_data: `project:::tool:::task:::${run_id}`,
    ...(counted ? { usage: counted } : {}),
  }
}

function saved_run(
  usage: Spend & { total_llm_latency_ms: number },
  trace: Trace = [],
): TaskRun {
  return { usage, trace } as TaskRun
}

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
    })
  })

  it("reads a counted subtask from the trace when its run was never saved", async () => {
    const fetch_run = fetcher({})

    const usage = await calculate_subtask_usage(
      [subtask_call("None", { cost: 0.01, total_tokens: 1050 })],
      fetch_run,
    )

    expect(fetch_run).not.toHaveBeenCalled()
    expect(usage).toMatchObject({ cost: 0.01, tokens: 1050, uncounted_cost: 0 })
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

  it("skips an older subtask whose run can't be loaded", async () => {
    const fetch_run = vi.fn(async (reference: SubtaskReference) => {
      if (reference.run_id === "deleted") throw new Error("not found")
      return saved_run({
        cost: 0.02,
        total_tokens: 20,
        total_llm_latency_ms: 5,
      })
    })
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    const usage = await calculate_subtask_usage(
      [subtask_call("deleted"), subtask_call("kept")],
      fetch_run,
    )

    expect(usage).toMatchObject({
      cost: 0.02,
      uncounted_cost: 0.02,
      tokens: 20,
    })
    warn.mockRestore()
  })
})
