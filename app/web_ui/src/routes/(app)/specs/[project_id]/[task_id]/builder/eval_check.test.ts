import { beforeEach, describe, expect, it, vi } from "vitest"
import { get } from "svelte/store"
import type { JudgeConfig } from "$lib/eval/default_judge"
import type { CachedGroundedCases } from "./builder_draft"

const POST = vi.fn()
vi.mock("$lib/api_client", () => ({ client: { POST } }))

const {
  answers_summary,
  batch_drops,
  case_excerpt,
  cases_per_fixture,
  clip,
  drops_by_reason,
  eval_check_key,
  eval_check_store,
  failure_grouping_request,
  failures_without_reasoning,
  fault_counts,
  fixture_label,
  fixture_row,
  grouping_offer_text,
  grouping_scope_text,
  has_judge_reasoning,
  headroom,
  headroom_text,
  load_failure_grouping,
  MAX_GROUPED_FAILURES,
  on_target_sentence,
  question_rows,
  rehearsal_check,
  rule_label,
  run_config_phrase,
  MIN_HEADROOM_CASES,
  TOO_EASY_PASS_RATE,
  TOO_HARD_PASS_RATE,
  WHOLE_EVAL_KEY,
} = await import("./eval_check")
type PanelCase = import("./eval_check").PanelCase
type FailureGrouping = import("./eval_check").FailureGrouping

function judged(
  id: string,
  judge_score: "pass" | "fail",
  extra: Partial<PanelCase> = {},
): PanelCase {
  return {
    trace_id: id,
    judge_score,
    judge_reasoning: `Reasoning for ${id}.`,
    raw_input: `input ${id}`,
    raw_output: `output ${id}`,
    trace: null,
    openenv_reset: null,
    judge_guidance: null,
    ...extra,
  }
}

function batch(passes: number, fails: number): PanelCase[] {
  return [
    ...Array.from({ length: passes }, (_, i) => judged(`p${i}`, "pass")),
    ...Array.from({ length: fails }, (_, i) => judged(`f${i}`, "fail")),
  ]
}

const judge: JudgeConfig = {
  prompt: "Judge it.",
  model_name: "claude_sonnet_4_6",
  model_provider: "anthropic",
  thinking_level: "high",
}

const grouping: FailureGrouping = {
  rule_summary: "asks before deleting",
  failures: [
    {
      case_id: "f0",
      fault_kind: "agent",
      group: "Dates shown in UTC",
      about_rule: false,
      evidence: "07/03 shown.",
    },
    {
      case_id: "f1",
      fault_kind: "agent",
      group: "Dates shown in UTC",
      about_rule: false,
      evidence: "07/04 shown.",
    },
    {
      case_id: "f2",
      fault_kind: "agent",
      group: "Deleted without asking",
      about_rule: true,
      evidence: "No confirm.",
    },
    {
      case_id: "f3",
      fault_kind: "reference",
      group: "Expected outcome too strict",
      about_rule: true,
      evidence: "Name format.",
    },
  ],
  groups: [
    {
      name: "Dates shown in UTC",
      fault_kind: "agent",
      about_rule: false,
      count: 2,
      example_case_id: "f0",
      example: "07/03 shown.",
    },
    {
      name: "Deleted without asking",
      fault_kind: "agent",
      about_rule: true,
      count: 1,
      example_case_id: "f2",
      example: "No confirm.",
    },
    {
      name: "Expected outcome too strict",
      fault_kind: "reference",
      about_rule: true,
      count: 1,
      example_case_id: "f3",
      example: "Name format.",
    },
  ],
  on_target_count: 1,
  failure_count: 4,
  texts_shortened: false,
}

describe("headroom", () => {
  it("has its thresholds at 85% and 10%", () => {
    expect(TOO_EASY_PASS_RATE).toBe(0.85)
    expect(TOO_HARD_PASS_RATE).toBe(0.1)
  })

  it.each([
    [59, 1, "too_easy"],
    [17, 3, "too_easy"],
    [16, 4, "ok"],
    [23, 17, "ok"],
    [2, 18, "too_hard"],
    [0, 20, "too_hard"],
  ])("%i passes and %i fails read as %s", (passes, fails, verdict) => {
    const h = headroom(batch(passes, fails))
    expect(h).toEqual({
      passed: passes,
      total: passes + fails,
      rate: passes / (passes + fails),
      verdict,
    })
  })

  it("is neutral on an empty batch", () => {
    expect(headroom([]).verdict).toBe("ok")
  })

  it.each([
    [9, 0, "ok"],
    [0, 9, "ok"],
    [1, 0, "ok"],
    [10, 0, "too_easy"],
    [0, 10, "too_hard"],
    [1, 9, "too_hard"],
    [9, 1, "too_easy"],
  ])(
    "needs at least 10 cases for a verdict: %i passes and %i fails read as %s",
    (passes, fails, verdict) => {
      expect(MIN_HEADROOM_CASES).toBe(10)
      expect(headroom(batch(passes, fails)).verdict).toBe(verdict)
    },
  )

  it("says what each verdict means", () => {
    expect(headroom_text(headroom(batch(59, 1)))).toContain("Too easy: 98%")
    expect(headroom_text(headroom(batch(1, 19)))).toContain(
      "Check for cases no agent can pass",
    )
    expect(headroom_text(headroom(batch(23, 17)))).toBe(
      "58% of the cases pass on the run config, so the eval has room to show a change.",
    )
  })

  it("offers a guard eval or a harder one when too easy, and names the run config", () => {
    expect(headroom_text(headroom(batch(59, 1)), "Haiku 5p5 v2")).toBe(
      'Too easy: 98% of the cases pass on run config "Haiku 5p5 v2". Keep it as a guard eval, or make it harder: at 85% or more, the eval can\'t show that a change made the agent better.',
    )
    expect(headroom_text(headroom(batch(1, 19)), "Haiku 5p5 v2")).toBe(
      'Check for cases no agent can pass: only 5% of the cases pass on run config "Haiku 5p5 v2".',
    )
  })

  it("never says baseline", () => {
    for (const [p, f] of [
      [59, 1],
      [1, 19],
      [23, 17],
    ]) {
      expect(headroom_text(headroom(batch(p, f)), "rc")).not.toMatch(
        /baseline/i,
      )
      expect(headroom_text(headroom(batch(p, f)))).not.toMatch(/baseline/i)
    }
  })

  it("falls back to 'the run config' with no name", () => {
    expect(run_config_phrase(null)).toBe("the run config")
    expect(run_config_phrase("  ")).toBe("the run config")
    expect(run_config_phrase("A")).toBe('run config "A"')
  })
})

describe("cases per fixture", () => {
  const reset = (reset_kwargs: Record<string, unknown>) => ({
    openenv_reset: { openenv_server_id: "s1", reset_kwargs },
  })

  it("labels a case by its reset arguments without the seed", () => {
    expect(
      fixture_label(reset({ fixture: "north", seed: 4 }).openenv_reset),
    ).toBe("north")
    expect(
      fixture_label(reset({ user: "ana", fixture: "north" }).openenv_reset),
    ).toBe("fixture=north, user=ana")
    expect(fixture_label(reset({ seed: 1 }).openenv_reset)).toBe(
      "Default reset",
    )
    expect(fixture_label(reset({ size: { rows: 2 } }).openenv_reset)).toBe(
      '{"rows":2}',
    )
  })

  it("counts cases per starting state, largest first", () => {
    const cases = [
      reset({ fixture: "a" }),
      reset({ fixture: "b", seed: 1 }),
      reset({ fixture: "b", seed: 2 }),
      reset({ fixture: "c" }),
    ]
    expect(cases_per_fixture(cases)).toEqual({
      rows: [
        { fixture: "b", count: 2, variants: [] },
        { fixture: "a", count: 1, variants: [] },
        { fixture: "c", count: 1, variants: [] },
      ],
      total: 4,
      crowded: null,
    })
  })

  it("warns when one starting state holds more than half the cases", () => {
    const cases = [
      reset({ fixture: "default" }),
      reset({ fixture: "default" }),
      reset({ fixture: "other" }),
    ]
    expect(cases_per_fixture(cases)?.crowded).toEqual({
      fixture: "default",
      count: 2,
      variants: [],
    })
  })

  it("is null when no case ran in an OpenEnv server", () => {
    expect(cases_per_fixture([{ openenv_reset: null }, {}])).toBeNull()
  })

  it("shows one row per fixture when grounding added other arguments", () => {
    // The shape of a real 66-case build: one fixture, four argument sets.
    const cases = [
      ...Array.from({ length: 30 }, () =>
        reset({ fixture: "big_co", now: "2026-09-01T14:00:00Z", seed: 7 }),
      ),
      ...Array.from({ length: 26 }, (_, i) =>
        reset({ fixture: "big_co", seed: i }),
      ),
      ...Array.from({ length: 7 }, () =>
        reset({
          fixture: "big_co",
          now: "2026-09-01T14:00:00Z",
          clock_mode: "fixed",
        }),
      ),
      ...Array.from({ length: 3 }, () =>
        reset({ fixture: "big_co", now: "2026-09-01T15:00:00Z" }),
      ),
    ]
    const spread = cases_per_fixture(cases)
    expect(spread?.rows).toEqual([
      {
        fixture: "big_co",
        count: 66,
        variants: [
          { label: "now=2026-09-01T14:00:00Z", count: 30 },
          { label: "no other arguments", count: 26 },
          { label: "clock_mode=fixed, now=2026-09-01T14:00:00Z", count: 7 },
          { label: "now=2026-09-01T15:00:00Z", count: 3 },
        ],
      },
    ])
    expect(spread?.total).toBe(66)
  })

  it("groups two fixtures apart, each with its own detail", () => {
    const spread = cases_per_fixture([
      reset({ fixture: "a", now: "t1" }),
      reset({ fixture: "a" }),
      reset({ fixture: "b", user: "ana" }),
    ])
    expect(spread?.rows).toEqual([
      {
        fixture: "a",
        count: 2,
        variants: [
          { label: "no other arguments", count: 1 },
          { label: "now=t1", count: 1 },
        ],
      },
      { fixture: "b", count: 1, variants: [{ label: "user=ana", count: 1 }] },
    ])
  })

  it("keeps the old rows on a server with no fixture argument", () => {
    const spread = cases_per_fixture([
      reset({ user: "ana", world: "x" }),
      reset({ user: "ana", world: "x", seed: 3 }),
      reset({ user: "bo", world: "x" }),
    ])
    expect(spread?.rows).toEqual([
      { fixture: "user=ana, world=x", count: 2, variants: [] },
      { fixture: "user=bo, world=x", count: 1, variants: [] },
    ])
    expect(fixture_row(reset({ seed: 1 }).openenv_reset)).toEqual({
      fixture: "Default reset",
      variant: null,
    })
  })
})

describe("rehearsal_check", () => {
  const rehearsed = (
    trace_id: string,
    rehearsal_score: "pass" | "fail" | null | undefined,
  ) => ({
    trace_id,
    raw_input: `Message ${trace_id}`,
    rehearsal_score,
    rehearsal_reasoning: rehearsal_score ? `Why ${trace_id}` : null,
  })

  it("is null until a case carries a rehearsal verdict", () => {
    expect(
      rehearsal_check([rehearsed("a", null), rehearsed("b", undefined)]),
    ).toBeNull()
  })

  it("counts over the judged rehearsals and lists the failed cases", () => {
    const check = rehearsal_check([
      rehearsed("a", "pass"),
      rehearsed("b", "fail"),
      rehearsed("c", null),
      rehearsed("d", "fail"),
    ])
    expect(check?.judged).toBe(3)
    expect(check?.failed.map((c) => c.trace_id)).toEqual(["b", "d"])
    expect(check?.failed[0].rehearsal_reasoning).toBe("Why b")
  })
})

describe("judge reasoning", () => {
  it("treats the server's no-reasoning placeholder as no reasoning", () => {
    expect(
      has_judge_reasoning(
        "The judge returned a FAIL verdict without an explicit reasoning trace.",
      ),
    ).toBe(false)
    expect(has_judge_reasoning("  ")).toBe(false)
    expect(has_judge_reasoning("It deleted without asking.")).toBe(true)
  })

  it("counts failures the grouping cannot read", () => {
    const cases = [
      judged("f0", "fail", { judge_reasoning: "" }),
      judged("f1", "fail"),
      judged("p0", "pass", { judge_reasoning: "" }),
    ]
    expect(failures_without_reasoning(cases)).toBe(1)
  })
})

describe("drops", () => {
  const drop = (drop_reason?: string) => ({
    scenario_index: 0,
    scenario: "s",
    drop_detail: "d",
    drop_reason,
  })

  it("counts drops by reason, with a missing reason read as didn't fit", () => {
    expect(
      drops_by_reason([drop("limit"), drop("no_fit"), drop(), drop("other")]),
    ).toEqual([
      { label: "didn't fit the environment", count: 2 },
      { label: "ran out of calls or time", count: 1 },
      { label: "other", count: 1 },
    ])
  })

  it("reads the drops of the grounded set the batch was driven from", () => {
    const cache = {
      prompts_json: '["a"]',
      drops: [drop("limit")],
    } as unknown as CachedGroundedCases
    expect(batch_drops(cache, '["a"]')).toHaveLength(1)
    expect(batch_drops(cache, '["b"]')).toEqual([])
    expect(batch_drops(null, '["a"]')).toEqual([])
  })
})

describe("failure grouping request", () => {
  it("sends each failure with reasoning, and nothing else", () => {
    const cases = [
      judged("p0", "pass"),
      judged("f0", "fail", { judge_guidance: "Asks first." }),
      judged("f1", "fail", { judge_reasoning: "" }),
    ]
    expect(failure_grouping_request(cases, "the spec", judge)).toEqual({
      spec_text: "the spec",
      judge,
      failures: [
        {
          case_id: "f0",
          judge_reasoning: "Reasoning for f0.",
          case_summary: "First message: input f0\nFinal reply: output f0",
          judge_guidance: "Asks first.",
        },
      ],
    })
  })

  it("is null with no failure to group", () => {
    expect(failure_grouping_request(batch(3, 0), "s", judge)).toBeNull()
    const no_reasoning = [judged("f0", "fail", { judge_reasoning: "" })]
    expect(failure_grouping_request(no_reasoning, "s", judge)).toBeNull()
  })

  it("caps the failures at what the server accepts", () => {
    const request = failure_grouping_request(
      batch(0, MAX_GROUPED_FAILURES + 5),
      "s",
      judge,
    )
    expect(request?.failures).toHaveLength(MAX_GROUPED_FAILURES)
  })

  it("takes the first user message and the last reply from the trace", () => {
    const excerpt = case_excerpt({
      raw_input: "raw in",
      raw_output: "raw out",
      trace: [
        { role: "system", content: "You are an agent." },
        { role: "user", content: "Delete the old ones." },
        { role: "assistant", content: "Which ones?" },
        { role: "user", content: [{ type: "text", text: "All of them." }] },
        { role: "assistant", content: "Done." },
      ],
    })
    expect(excerpt).toBe(
      "First message: Delete the old ones.\nFinal reply: Done.",
    )
  })

  it("clips long text in the middle, keeping both ends", () => {
    expect(clip("short", 10)).toBe("short")
    const clipped = clip(`start${"x".repeat(100)}end`, 25)
    expect(clipped.startsWith("start")).toBe(true)
    expect(clipped.endsWith("end")).toBe(true)
    expect(clipped).toContain("[…]")
    expect(clipped.length).toBeLessThanOrEqual(25)
  })

  it("keys a batch to its verdicts, its judged spec and its round", () => {
    const cases = batch(1, 1)
    const flipped = [cases[0], { ...cases[1], judge_score: "pass" as const }]
    const key = eval_check_key(cases, "spec", 0)
    expect(eval_check_key(batch(1, 1), "spec", 0)).toBe(key)
    expect(eval_check_key(flipped, "spec", 0)).not.toBe(key)
    expect(eval_check_key(cases, "other spec", 0)).not.toBe(key)
    expect(eval_check_key(cases, "spec", 1)).not.toBe(key)
  })
})

describe("load_failure_grouping", () => {
  // A braced body: a function returned from beforeEach runs as its teardown.
  beforeEach(() => {
    POST.mockReset()
  })
  const body = { spec_text: "s", judge, failures: [] }

  it("is ready with the server's grouping", async () => {
    POST.mockResolvedValue({ data: grouping, error: undefined })
    const result = await load_failure_grouping("p1", "t1", body)
    expect(result).toEqual({
      status: "ready",
      grouping,
    })
    expect(POST).toHaveBeenCalledWith(
      "/api/projects/{project_id}/tasks/{task_id}/eval_builder/group_failures",
      { params: { path: { project_id: "p1", task_id: "t1" } }, body },
    )
  })

  it("is unavailable, with the server's message, when the call fails", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { message: { code: "grouping_failed", message: "Too slow." } },
    })
    const result = await load_failure_grouping("p1", "t1", body)
    expect(result).toEqual({
      status: "unavailable",
      message: "Too slow.",
    })
  })

  it("is unavailable, never a throw, when the server can't be reached", async () => {
    POST.mockRejectedValue(new TypeError("fetch failed"))
    const result = await load_failure_grouping("p1", "t1", body)
    expect(result).toEqual({
      status: "unavailable",
      message: "fetch failed",
    })
  })
})

describe("eval_check_store", () => {
  const request = { spec_text: "s", judge, failures: [] }
  const ready = { status: "ready" as const, grouping }

  // A grouping call the test answers by hand, to order the answers.
  function pending_calls() {
    const answers: ((state: typeof ready) => void)[] = []
    const load = vi.fn(
      () =>
        new Promise<typeof ready>((resolve) => {
          answers.push(resolve)
        }),
    )
    return { load, answers }
  }

  it("never calls the model on its own", () => {
    const { load } = pending_calls()
    const store = eval_check_store(load)
    store.set_batch("A")
    store.leave()
    store.set_batch("B")
    expect(load).not.toHaveBeenCalled()
    expect(get(store).grouping).toEqual({ status: "idle" })
  })

  it("drops a grouping for an earlier batch that lands late", async () => {
    const { load, answers } = pending_calls()
    const store = eval_check_store(load)
    store.set_batch("A")
    const call_a = store.group("p1", "t1", request)
    expect(get(store).grouping).toEqual({ status: "loading" })

    store.set_batch("B")
    const call_b = store.group("p1", "t1", request)
    answers[1](ready)
    await call_b
    answers[0]({ ...ready, grouping: { ...grouping, rule_summary: "old" } })
    await call_a

    expect(get(store)).toEqual({ key: "B", grouping: ready, answers: {} })
  })

  it("drops a running grouping when the owner leaves, and can start again", async () => {
    const { load, answers } = pending_calls()
    const store = eval_check_store(load)
    store.set_batch("A")
    const first = store.group("p1", "t1", request)
    store.leave()
    expect(get(store).grouping).toEqual({ status: "idle" })
    answers[0](ready)
    await first
    expect(get(store).grouping).toEqual({ status: "idle" })

    const second = store.group("p1", "t1", request)
    answers[1](ready)
    await second
    expect(get(store).grouping).toEqual(ready)
  })

  it("keeps a finished grouping when the owner comes back to the same batch", async () => {
    const store = eval_check_store(vi.fn().mockResolvedValue(ready))
    store.set_batch("A")
    await store.group("p1", "t1", request)
    store.leave()
    store.set_batch("A")
    expect(get(store).grouping).toEqual(ready)
    store.set_batch("B")
    expect(get(store).grouping).toEqual({ status: "idle" })
  })

  it("lets the owner retry a failed grouping", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce({ status: "unavailable", message: "Too slow." })
      .mockResolvedValueOnce(ready)
    const store = eval_check_store(load)
    store.set_batch("A")
    await store.group("p1", "t1", request)
    expect(get(store).grouping).toEqual({
      status: "unavailable",
      message: "Too slow.",
    })
    await store.group("p1", "t1", request)
    expect(get(store).grouping).toEqual(ready)
  })

  it("keeps the owner's answers through Start, and clears them on a new batch", () => {
    const store = eval_check_store(vi.fn())
    store.set_batch("A")
    store.set_answers({ [WHOLE_EVAL_KEY]: "should_be_harder" })
    // Start unmounts the panel; the page keeps showing the same batch.
    store.leave()
    store.set_batch("A")
    expect(get(store).answers).toEqual({ [WHOLE_EVAL_KEY]: "should_be_harder" })
    store.set_batch("B")
    expect(get(store).answers).toEqual({})
  })

  it("is unavailable, with no call, when there is nothing to send", async () => {
    const load = vi.fn()
    const store = eval_check_store(load)
    store.set_batch("A")
    await store.group("p1", "t1", null)
    expect(load).not.toHaveBeenCalled()
    expect(get(store).grouping.status).toBe("unavailable")
  })
})

describe("reading the grouping", () => {
  it("counts failures by fault kind, unknown only when present", () => {
    expect(fault_counts(grouping).map((r) => [r.label, r.count])).toEqual([
      ["Agent", 3],
      ["Reference", 1],
      ["Judge", 0],
      ["World", 0],
      ["Simulated user", 0],
    ])
  })

  it("states the on-target share and the largest other group", () => {
    expect(on_target_sentence(grouping)).toBe(
      '1 of 4 grouped failures are about "asks before deleting". 2 are about "Dates shown in UTC", the largest other group.',
    )
    const all_on_target = {
      ...grouping,
      groups: [grouping.groups[1]],
      on_target_count: 1,
      failure_count: 1,
    }
    expect(on_target_sentence(all_on_target)).toBe(
      '1 of 1 grouped failure is about "asks before deleting".',
    )
  })

  it("says how many failures the grouping sorts, and what it reads", () => {
    expect(grouping_offer_text(12, 10)).toMatch(
      /^Sort 10 of 12 failures by cause with one call to the judge's model\. It reads the judge's own reasoning/,
    )
    expect(grouping_offer_text(130, 120)).toContain(
      "Sort 100 of 130 failures by cause with one call to the judge's model. One call takes at most 100: the first 100 in batch order.",
    )
    expect(grouping_scope_text(grouping, 6)).toMatch(
      /^Grouped 4 of 6 failures\./,
    )
    expect(grouping_scope_text(grouping, 6)).not.toContain("shortened")
    expect(
      grouping_scope_text({ ...grouping, texts_shortened: true }, 4),
    ).toContain("Long texts were shortened to fit one call.")
  })

  it("names the rule from the grouping, else from the spec's first line", () => {
    expect(rule_label("spec", { status: "ready", grouping })).toBe(
      "asks before deleting",
    )
    expect(
      rule_label("Ask before deleting.\nMore detail.", { status: "loading" }),
    ).toBe("Ask before deleting")
    expect(rule_label("x".repeat(200), { status: "idle" })).toHaveLength(160)
  })

  it("asks about the whole eval, then each group once the grouping is ready", () => {
    const h = headroom(batch(23, 17))
    expect(question_rows(h, { status: "loading" })).toEqual([
      { key: WHOLE_EVAL_KEY, label: "The whole eval (58% pass)" },
    ])
    expect(
      question_rows(h, { status: "ready", grouping }).map((r) => r.key),
    ).toEqual([
      WHOLE_EVAL_KEY,
      "Dates shown in UTC",
      "Deleted without asking",
      "Expected outcome too strict",
    ])
  })
})

describe("answers_summary", () => {
  it("is null with no answer", () => {
    expect(answers_summary({})).toBeNull()
  })

  it("names each answer, the whole eval first", () => {
    expect(
      answers_summary({
        "Deleted without asking": "in_scope",
        [WHOLE_EVAL_KEY]: "should_be_harder",
      }),
    ).toBe(
      "Your answers on the eval check: the whole eval: Should Be Harder; Deleted without asking: In Scope.",
    )
  })
})
