// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import EvalCheckPanel from "./eval_check_panel.svelte"
import type {
  FailureGrouping,
  FailureGroupingState,
  PanelCase,
} from "./eval_check"

afterEach(() => cleanup())

function judged(
  id: string,
  judge_score: "pass" | "fail",
  fixture = "north",
): PanelCase {
  return {
    trace_id: id,
    judge_score,
    judge_reasoning: `Reasoning for ${id}.`,
    raw_input: "in",
    raw_output: "out",
    trace: null,
    openenv_reset: { openenv_server_id: "s1", reset_kwargs: { fixture } },
    judge_guidance: null,
  }
}

function batch(passes: number, fails: number): PanelCase[] {
  return [
    ...Array.from({ length: passes }, (_, i) => judged(`p${i}`, "pass")),
    ...Array.from({ length: fails }, (_, i) =>
      judged(`f${i}`, "fail", i % 2 ? "south" : "east"),
    ),
  ]
}

const grouping: FailureGrouping = {
  rule_summary: "asks before deleting",
  failures: [
    {
      case_id: "f0",
      fault_kind: "agent",
      group: "Deleted without asking",
      about_rule: true,
      evidence: "No confirm.",
    },
    {
      case_id: "f1",
      fault_kind: "judge",
      group: "Judge applied a rule not in the spec",
      about_rule: false,
      evidence: "Failed it for tone.",
    },
  ],
  groups: [
    {
      name: "Deleted without asking",
      fault_kind: "agent",
      about_rule: true,
      count: 1,
      example_case_id: "f0",
      example: "No confirm.",
    },
    {
      name: "Judge applied a rule not in the spec",
      fault_kind: "judge",
      about_rule: false,
      count: 1,
      example_case_id: "f1",
      example: "Failed it for tone.",
    },
  ],
  on_target_count: 1,
  failure_count: 2,
  texts_shortened: false,
}

function show(
  cases: PanelCase[],
  state: FailureGroupingState,
  extra: Record<string, unknown> = {},
) {
  return render(EvalCheckPanel, {
    props: {
      cases,
      grouping: state,
      spec_text: "The agent asks before it deletes a record.\nMore detail.",
      judged_noun: "conversation",
      ...extra,
    },
  })
}

function text(container: HTMLElement): string {
  return (container.textContent ?? "").replace(/\s+/g, " ")
}

function question_labels(container: HTMLElement): string[] {
  return [
    ...container.querySelectorAll("[data-owner-question] tr td:first-child"),
  ].map((td) => (td.textContent ?? "").trim())
}

describe("EvalCheckPanel", () => {
  it("with zero failures, flags a too-easy eval and still asks the question", () => {
    const { container } = show(batch(10, 0), { status: "idle" })
    const all = text(container)
    expect(all).toContain("Pass Rate")
    expect(all).toContain("100% (10 of 10 conversations pass)")
    expect(all).toContain("Too easy: 100% of the baseline's cases pass.")
    expect(all).toContain("No failures to sort: every conversation passed.")
    expect(container.querySelector("[data-who-failed]")).toBeNull()
    expect(all).toContain(
      "This eval is meant to measure: The agent asks before it deletes a record.",
    )
    expect(question_labels(container)).toEqual(["The whole eval (100% pass)"])
  })

  it("with all failures and a grouping, shows who and what failed", () => {
    const { container } = show(batch(0, 2), { status: "ready", grouping })
    const all = text(container)
    expect(all).toContain("Check for cases no agent can pass")
    expect(all).toContain("Grouped 2 of 2 failures.")
    expect(all).toContain("it can miss a fault in the judge itself")
    const who = [
      ...container.querySelectorAll("[data-who-failed] tbody tr"),
    ].map((tr) => (tr.textContent ?? "").replace(/\s+/g, " ").trim())
    expect(who).toEqual([
      "Agent 1",
      "Reference 0",
      "Judge 1",
      "World 0",
      "Simulated user 0",
    ])
    const what = container.querySelectorAll("[data-what-failed] tbody tr")
    expect(what).toHaveLength(2)
    expect(what[0].textContent).toContain("Deleted without asking")
    expect(what[0].textContent).toContain("No confirm.")
    expect(what[0].textContent).toContain("Yes")
    expect(what[1].textContent).toContain("No")
    expect(
      container.querySelector("[data-on-target]")?.textContent?.trim(),
    ).toBe(
      '1 of 2 grouped failures are about "asks before deleting". 1 is about "Judge applied a rule not in the spec", the largest other group.',
    )
    expect(all).toContain(
      "This eval is meant to measure: asks before deleting.",
    )
    expect(question_labels(container)).toEqual([
      "The whole eval (0% pass)",
      "Deleted without asking (1)",
      "Judge applied a rule not in the spec (1)",
    ])
  })

  it("when grouping is unavailable, says so and keeps the rest", () => {
    const { container } = show(batch(5, 5), {
      status: "unavailable",
      message: "The grouping call took too long.",
    })
    const all = text(container)
    expect(all).toContain(
      "Grouping unavailable: The grouping call took too long. The numbers above still hold.",
    )
    expect(all).toContain("50% (5 of 10 conversations pass)")
    expect(container.querySelector("[data-fixtures]")).not.toBeNull()
    expect(question_labels(container)).toEqual(["The whole eval (50% pass)"])
    expect(text(container)).toContain("Try Again")
  })

  it("starts the grouping only from its button", async () => {
    const on_group_failures = vi.fn()
    const { container } = show(
      batch(5, 5),
      { status: "idle" },
      { on_group_failures },
    )
    expect(on_group_failures).not.toHaveBeenCalled()
    expect(text(container)).toContain(
      "Sort 5 of 5 failures by cause with one call to the judge's model.",
    )
    const button = [...container.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "Group the Failures",
    )!
    await fireEvent.click(button)
    expect(on_group_failures).toHaveBeenCalledOnce()
  })

  it("offers no grouping when every case passed", () => {
    const { container } = show(batch(5, 0), { status: "idle" })
    expect(text(container)).not.toContain("Group the Failures")
  })

  it("tells the page when it leaves the screen", () => {
    const on_leave = vi.fn()
    const { unmount } = show(batch(5, 5), { status: "loading" }, { on_leave })
    expect(on_leave).not.toHaveBeenCalled()
    unmount()
    expect(on_leave).toHaveBeenCalledOnce()
  })

  it("shows that the grouping is still running", () => {
    const { container } = show(batch(5, 5), { status: "loading" })
    expect(
      container.querySelector("[data-grouping-status]")?.textContent?.trim(),
    ).toBe("Sorting the failures by cause.")
  })

  it("says why failures are not grouped when none has reasoning", () => {
    const cases = batch(5, 2).map((c) =>
      c.judge_score === "fail" ? { ...c, judge_reasoning: "" } : c,
    )
    const all = text(show(cases, { status: "idle" }).container)
    expect(all).toContain(
      "2 of 2 failures have no judge reasoning, so they can't be sorted by cause. To get reasoning, choose a higher Judge Thinking Level in Generation Settings",
    )
    expect(all).toContain("No failure has judge reasoning to sort by cause.")
  })

  it("lists cases per starting state and warns when one holds over half", () => {
    const { container } = show(batch(6, 2), { status: "loading" })
    const rows = [
      ...container.querySelectorAll("[data-fixtures] tbody tr"),
    ].map((tr) => (tr.textContent ?? "").replace(/\s+/g, " ").trim())
    expect(rows).toEqual(["north 6", "east 1", "south 1"])
    expect(text(container)).toContain(
      "One starting state holds 6 of 8 cases: north.",
    )
  })

  it("shows drops by reason", () => {
    const cases = batch(3, 1)
    const drop = (drop_reason: string) => ({
      scenario_index: 0,
      scenario: "s",
      drop_detail: "d",
      drop_reason,
    })
    const all = text(
      show(
        cases,
        { status: "loading" },
        {
          drops: [drop("limit"), drop("no_fit"), drop("no_fit")],
        },
      ).container,
    )
    expect(all).toContain(
      "2 didn't fit the environment, 1 ran out of calls or time",
    )
  })

  it("hands every answer so far to the callback, one pick per row", async () => {
    const on_answers_change = vi.fn()
    const { container, component } = show(
      batch(0, 2),
      { status: "ready", grouping },
      { on_answers_change },
    )
    // The page holds the answers and hands them back, as +page.svelte does.
    on_answers_change.mockImplementation((answers) =>
      component.$set({ answers }),
    )
    const rows = container.querySelectorAll("[data-owner-question] tbody tr")
    const button = (row: number, label: string) =>
      [...rows[row].querySelectorAll("button")].find(
        (b) => b.textContent?.trim() === label,
      )!

    await fireEvent.click(button(0, "Should Be Harder"))
    await fireEvent.click(button(2, "Out of Scope"))
    await fireEvent.click(button(2, "Reference Is Wrong"))

    expect(on_answers_change).toHaveBeenLastCalledWith({
      "": "should_be_harder",
      "Judge applied a rule not in the spec": "reference_is_wrong",
    })
    expect(button(2, "Reference Is Wrong").className).toContain("btn-secondary")
    expect(button(2, "Reference Is Wrong").getAttribute("aria-pressed")).toBe(
      "true",
    )
    expect(button(2, "Out of Scope").className).toContain("btn-outline")
    expect(button(1, "In Scope").className).toContain("btn-outline")
    expect(
      container.querySelector("[data-answers-summary]")?.textContent?.trim(),
    ).toBe(
      "Your answers on the eval check: the whole eval: Should Be Harder; Judge applied a rule not in the spec: Reference Is Wrong.",
    )
  })

  it("shows the answers the page kept when it comes back", () => {
    const { container } = show(
      batch(0, 2),
      { status: "ready", grouping },
      { answers: { "Deleted without asking": "out_of_scope" } },
    )
    const pressed = [
      ...container.querySelectorAll(
        '[data-owner-question] [aria-pressed="true"]',
      ),
    ].map((b) => b.textContent?.trim())
    expect(pressed).toEqual(["Out of Scope"])
  })
})
