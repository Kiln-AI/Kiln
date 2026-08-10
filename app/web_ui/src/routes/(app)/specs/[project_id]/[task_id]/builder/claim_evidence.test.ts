import { describe, expect, it } from "vitest"
import {
  all_traces_reviewed,
  apply_rejudge_results,
  blind_final_judgement,
  build_claim_review_payload,
  build_graded_traces,
  build_trace_reviews,
  calibration_gate_target,
  disagreed_trace_indices,
  disagreement_feedback,
  final_judgement_reason,
  flipped_indices,
  grade_disagreement_count,
  has_grade_disagreement,
  is_trace_reviewed,
  map_output_span_to_trace,
  MAX_JUDGE_PROMPT_CHARS,
  plan_save_action,
  refine_judge_tooltip,
  rejudge_shortfall_notice,
  review_cta,
  resolve_citation_span,
  review_target,
  reviewed_trace_count,
  select_calibration_subset,
  select_review_subset,
  silent_refine_at_save,
  user_says_meets_spec,
  validate_refined_judge_prompt,
  type Claim,
  type RejudgeCaseResult,
  type TraceClaims,
  type TraceReview,
} from "./claim_evidence"

function claim(overrides: Partial<Claim> = {}): Claim {
  return {
    claim: "The agent stated a return window as fact.",
    expected_result: "fail",
    evidence: "The reply gives 30 days [1].",
    citations: [
      { marker: 1, source: "output", from: "30 days", to: "30 days" },
    ],
    ...overrides,
  }
}

function trace(overrides: Partial<TraceClaims> = {}): TraceClaims {
  return {
    trace_id: "trace_0",
    leaf_run_id: null,
    raw_input: "What's the return window?",
    raw_output: "Our return window is 30 days.",
    judge_score: "fail",
    judge_reasoning: "Fabricated the window.",
    claims: [claim()],
    final_judgement: claim({
      claim: "Fails Eval: fabricated policy.",
      expected_result: "fail",
    }),
    claims_state: "built",
    claims_error: null,
    ...overrides,
  }
}

describe("build_trace_reviews", () => {
  it("creates one positional verdict per claim plus the final judgement slot", () => {
    const reviews = build_trace_reviews([trace({ claims: [claim(), claim()] })])
    expect(reviews[0].claim_verdicts).toHaveLength(2)
    expect(reviews[0].final_judgement_verdict).toEqual({
      agrees: null,
      why: "",
    })
  })

  it("handles empty claims (trivial evals)", () => {
    const reviews = build_trace_reviews([trace({ claims: [] })])
    expect(reviews[0].claim_verdicts).toHaveLength(0)
    expect(reviews[0].final_judgement_verdict.agrees).toBeNull()
  })
})

describe("is_trace_reviewed", () => {
  it("requires the final judgement verdict", () => {
    const t = trace()
    const review = build_trace_reviews([t])[0]
    expect(is_trace_reviewed(t, review)).toBe(false)
    review.final_judgement_verdict.agrees = true
    expect(is_trace_reviewed(t, review)).toBe(true)
  })

  it("requires a why on any disagreement, including the final judgement", () => {
    const t = trace()
    const review = build_trace_reviews([t])[0]
    review.final_judgement_verdict.agrees = false
    expect(is_trace_reviewed(t, review)).toBe(false)
    review.final_judgement_verdict.why = "The policy is real."
    expect(is_trace_reviewed(t, review)).toBe(true)
    review.claim_verdicts[0].agrees = false
    expect(is_trace_reviewed(t, review)).toBe(false)
    review.claim_verdicts[0].why = "Wrong claim."
    expect(is_trace_reviewed(t, review)).toBe(true)
  })

  it("is reviewable with an empty claims list via the final judgement alone", () => {
    const t = trace({ claims: [] })
    const review = build_trace_reviews([t])[0]
    review.final_judgement_verdict.agrees = true
    expect(is_trace_reviewed(t, review)).toBe(true)
    expect(all_traces_reviewed([t], [review])).toBe(true)
  })
})

describe("user_says_meets_spec", () => {
  function reviewed(agrees: boolean): TraceReview {
    return {
      trace_id: "trace_0",
      claim_verdicts: [{ agrees: null, why: "" }],
      final_judgement_verdict: { agrees, why: agrees ? "" : "disagree why" },
    }
  }

  it("anchors to judge_score (the pinned final-judgement verdict)", () => {
    expect(user_says_meets_spec(trace(), reviewed(true))).toBe(false)
    const passing = trace({
      judge_score: "pass",
      final_judgement: claim({ expected_result: "pass" }),
    })
    expect(user_says_meets_spec(passing, reviewed(true))).toBe(true)
  })

  it("flips the verdict when the human disagrees with the final judgement", () => {
    expect(user_says_meets_spec(trace(), reviewed(false))).toBe(true)
    const passing = trace({
      judge_score: "pass",
      final_judgement: claim({ expected_result: "pass" }),
    })
    expect(user_says_meets_spec(passing, reviewed(false))).toBe(false)
  })
})

describe("review_target", () => {
  it("is N//4 with a floor of one", () => {
    expect(review_target(40)).toBe(10)
    expect(review_target(38)).toBe(9)
    expect(review_target(4)).toBe(1)
    expect(review_target(3)).toBe(1)
    expect(review_target(1)).toBe(1)
    expect(review_target(0)).toBe(0)
  })
})

describe("select_review_subset", () => {
  function batch(
    scores: ("pass" | "fail")[],
  ): Pick<TraceClaims, "judge_score">[] {
    return scores.map((judge_score) => ({ judge_score }))
  }

  it("selects everything when the target covers the batch", () => {
    expect(select_review_subset(batch(["pass"]))).toEqual([0])
  })

  it("prefers a judge-fail for a tiny batch's single slot", () => {
    expect(select_review_subset(batch(["pass", "fail", "pass"]))).toEqual([1])
  })

  it("stratifies ~50/50 across judge verdicts at 40", () => {
    // 20 passes then 20 fails: 10 selected, 5 from each bucket.
    const traces = batch([
      ...Array(20).fill("pass"),
      ...Array(20).fill("fail"),
    ] as ("pass" | "fail")[])
    const picked = select_review_subset(traces)
    expect(picked).toHaveLength(10)
    const fails = picked.filter((i) => traces[i].judge_score === "fail")
    expect(fails).toHaveLength(5)
    // Spread across plan order, not clustered at the front.
    expect(picked.some((i) => i >= 30)).toBe(true)
    expect(picked.some((i) => i < 10)).toBe(true)
  })

  it("tops up from the other bucket when one is short", () => {
    // 39 passes, 1 fail: the fail is always picked, passes fill to 10.
    const traces = batch([...Array(39).fill("pass"), "fail"] as (
      | "pass"
      | "fail"
    )[])
    const picked = select_review_subset(traces)
    expect(picked).toHaveLength(10)
    expect(picked).toContain(39)
  })

  it("handles single-verdict batches (all pass)", () => {
    const traces = batch(Array(12).fill("pass") as ("pass" | "fail")[])
    const picked = select_review_subset(traces)
    expect(picked).toHaveLength(3)
    expect(new Set(picked).size).toBe(3)
  })

  it("is deterministic", () => {
    const traces = batch([
      "pass",
      "fail",
      "pass",
      "fail",
      "pass",
      "fail",
      "pass",
      "fail",
    ])
    expect(select_review_subset(traces)).toEqual(select_review_subset(traces))
  })
})

describe("reviewed_trace_count", () => {
  it("counts reviewed traces only (the save-gate numerator)", () => {
    const traces = [trace(), trace({ trace_id: "trace_1" })]
    const reviews = build_trace_reviews(traces)
    expect(reviewed_trace_count(traces, reviews)).toBe(0)
    reviews[0].final_judgement_verdict.agrees = true
    expect(reviewed_trace_count(traces, reviews)).toBe(1)
  })
})

describe("blind_final_judgement (failed claims build)", () => {
  it("pins the verdict to judge_score and demotes judge_reasoning, no citations", () => {
    const t = trace({
      claims: null,
      final_judgement: null,
      claims_state: "error",
      claims_error: "boom",
      judge_score: "fail",
      judge_reasoning: "The agent leaked the discount policy.",
    })
    const fj = blind_final_judgement(t)
    expect(fj.expected_result).toBe("fail")
    expect(fj.claim).toBe("The agent leaked the discount policy.")
    expect(fj.evidence).toBe("")
    expect(fj.citations).toEqual([])
  })
})

describe("errored-build trace is gradable on the blind verdict", () => {
  // A trace whose claims build failed has no claim slots, but the overall
  // verdict is still answerable — setting it makes the trace count toward
  // the save gate, the only recovery short of a paid re-drive.
  const errored = () =>
    trace({
      claims: null,
      final_judgement: null,
      claims_state: "error",
      claims_error: "boom",
    })

  it("is_trace_reviewed accepts it once the final verdict is set", () => {
    const t = errored()
    const review = build_trace_reviews([t])[0]
    expect(review.claim_verdicts).toHaveLength(0)
    expect(is_trace_reviewed(t, review)).toBe(false)
    review.final_judgement_verdict.agrees = true
    expect(is_trace_reviewed(t, review)).toBe(true)
  })

  it("counts toward the save gate so it stays reachable", () => {
    const t = errored()
    const reviews = build_trace_reviews([t])
    expect(reviewed_trace_count([t], reviews)).toBe(0)
    reviews[0].final_judgement_verdict.agrees = false
    reviews[0].final_judgement_verdict.why = "The judge was wrong."
    expect(reviewed_trace_count([t], reviews)).toBe(1)
  })
})

describe("build_claim_review_payload", () => {
  it("throws before claims are built (unbuilt traces cannot be graded)", () => {
    const t = trace({
      claims: null,
      final_judgement: null,
      claims_state: "unbuilt",
    })
    const review = build_trace_reviews([t])[0]
    expect(() => build_claim_review_payload(t, review)).toThrow(/built/)
  })

  it("includes only graded claims and always the final judgement", () => {
    const t = trace({ claims: [claim(), claim({ expected_result: "pass" })] })
    const review: TraceReview = {
      trace_id: "trace_0",
      claim_verdicts: [
        { agrees: true, why: "" },
        { agrees: null, why: "" }, // ungraded — excluded
      ],
      final_judgement_verdict: { agrees: false, why: "Policy is real." },
    }
    const payload = build_claim_review_payload(t, review)
    expect(payload.judge_score).toBe("fail")
    expect(payload.judge_reasoning).toBe("Fabricated the window.")
    expect(payload.claims).toHaveLength(1)
    expect(payload.claims[0].human_grade).toBe("agree")
    expect(payload.claims[0].human_feedback).toBeNull()
    expect(payload.final_judgement.human_grade).toBe("disagree")
    expect(payload.final_judgement.human_feedback).toBe("Policy is real.")
    expect(payload.final_judgement.expected_result).toBe("fail")
  })
})

describe("disagreement_feedback", () => {
  it("concatenates disagree whys across claims and the final judgement", () => {
    const review: TraceReview = {
      trace_id: "trace_0",
      claim_verdicts: [
        { agrees: false, why: "claim why" },
        { agrees: true, why: "ignored" },
      ],
      final_judgement_verdict: { agrees: false, why: "final why" },
    }
    expect(disagreement_feedback(review)).toBe("claim why final why")
  })
})

describe("build_graded_traces", () => {
  it("includes only reviewed traces and labels them by run id, else trace id", () => {
    const reviewed_t = trace({ leaf_run_id: "leaf-abc" })
    const reviewed_review: TraceReview = {
      trace_id: "trace_0",
      claim_verdicts: [{ agrees: true, why: "" }],
      final_judgement_verdict: { agrees: false, why: "policy is real" },
    }
    const half_t = trace({ trace_id: "trace_1", leaf_run_id: null })
    const half_review = build_trace_reviews([half_t])[0] // ungraded final → excluded

    const graded = build_graded_traces(
      [reviewed_t, half_t],
      [reviewed_review, half_review],
    )
    expect(graded).toHaveLength(1)
    expect(graded[0].trace_label).toBe("leaf-abc")
    expect(graded[0].final_judgement.human_grade).toBe("disagree")
    // Falls back to the client trace id when no durable run id exists.
    const single = build_graded_traces(
      [half_t],
      [
        {
          trace_id: "trace_1",
          claim_verdicts: [{ agrees: true, why: "" }],
          final_judgement_verdict: { agrees: true, why: "" },
        },
      ],
    )
    expect(single[0].trace_label).toBe("trace_1")
  })
})

describe("validate_refined_judge_prompt", () => {
  it("accepts a plain-text prompt", () => {
    expect(
      validate_refined_judge_prompt(
        "PASS if the reply is polite, FAIL otherwise.",
      ),
    ).toBeNull()
  })

  it("rejects empty / whitespace-only prompts", () => {
    expect(validate_refined_judge_prompt("")).toMatch(/empty/)
    expect(validate_refined_judge_prompt("   \n ")).toMatch(/empty/)
  })

  it("rejects Jinja/template braces and code fences", () => {
    expect(validate_refined_judge_prompt("Score {{ trace }}")).toMatch(/Jinja/)
    expect(validate_refined_judge_prompt("{% if x %}pass{% endif %}")).toMatch(
      /Jinja/,
    )
    expect(validate_refined_judge_prompt("{# comment #} judge")).toMatch(
      /Jinja/,
    )
    expect(validate_refined_judge_prompt("```\nrubric\n```")).toMatch(/fences/)
  })

  it("rejects an oversized prompt", () => {
    expect(
      validate_refined_judge_prompt("a".repeat(MAX_JUDGE_PROMPT_CHARS + 1)),
    ).toMatch(/too long/)
  })
})

describe("resolve_citation_span", () => {
  it("resolves from/to anchors in order", () => {
    const span = resolve_citation_span(
      "return window is 30 days from purchase",
      {
        from: "30 days",
        to: "purchase",
      },
    )
    expect(span).toEqual({ start: 17, end: 38 })
  })

  it("returns null when an anchor is missing", () => {
    expect(
      resolve_citation_span("no anchors here", { from: "30 days", to: "x" }),
    ).toBeNull()
  })
})

describe("final_judgement_reason — the verdict card's reason line", () => {
  it("renders the contract's reason-only line verbatim", () => {
    expect(
      final_judgement_reason(
        "The agent fabricated a return policy and repeated it under pressure.",
      ),
    ).toBe(
      "The agent fabricated a return policy and repeated it under pressure.",
    )
  })

  it("empty and whitespace-only reasons yield no text (evidence steps in)", () => {
    // "" is the contract's nothing-to-say value — also what the server's
    // synthesized backstop emits — and the ONLY fallback trigger.
    expect(final_judgement_reason("")).toBe("")
    expect(final_judgement_reason("   ")).toBe("")
  })

  it("legacy verdict-phrased output renders verbatim — enforcement is server-side", () => {
    // Pre-contract captures (and any model regression) show their text
    // as-is; the prompt's no-verdict-phrasing rule is tested where it
    // lives, in kiln_server.
    expect(final_judgement_reason("Eval passes per the judge's verdict.")).toBe(
      "Eval passes per the judge's verdict.",
    )
  })
})

describe("map_output_span_to_trace — flattener block layout port", () => {
  // A trace exercising every block kind the formatter emits: a plain user
  // turn, a reasoning-only assistant turn, a tool-call turn, its tool result,
  // and a final content turn.
  const trace = [
    { role: "user", content: "What is the return window?" },
    { role: "assistant", reasoning_content: "Let me think about policy." },
    {
      role: "assistant",
      content: null,
      tool_calls: [
        {
          id: "call_1",
          type: "function",
          function: { name: "lookup_policy", arguments: '{"q":1}' },
        },
      ],
    },
    { role: "tool", tool_call_id: "call_1", content: "30 day window" },
    { role: "assistant", content: "Our return window is 30 days." },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ] as any[]

  // Build raw_output exactly the way the server flattener does: one block per
  // emitted message, joined by a blank line.
  const raw_output = [
    "user:\n<user_message>\nWhat is the return window?\n</user_message>",
    "assistant reasoning:\n<assistant_reasoning_message>\nLet me think about policy.\n</assistant_reasoning_message>",
    'assistant requested tool calls:\n<assistant_requested_tool_calls>\n- Tool Name: lookup_policy\n- Arguments: {"q":1}\n</assistant_requested_tool_calls>',
    "tool:\n<tool_tool_message>\n30 day window\n</tool_tool_message>",
    "assistant:\n<assistant_message>\nOur return window is 30 days.\n</assistant_message>",
  ].join("\n\n")

  function map(from: string, to: string) {
    const span = resolve_citation_span(raw_output, { from, to })
    expect(span).not.toBeNull()
    return map_output_span_to_trace(trace, raw_output, span!)
  }

  it("maps a span in a chat (content) turn", () => {
    // `from` unique to the final turn — "return window" also appears in the
    // user turn, and resolve_citation_span anchors on the FIRST occurrence.
    const h = map("Our return", "30 days")
    expect(h).not.toBeNull()
    expect(h!.trace_index).toBe(4)
    expect(h!.kind).toBe("content")
    expect("Our return window is 30 days.".slice(h!.start, h!.end)).toBe(
      "Our return window is 30 days",
    )
  })

  it("maps a span in a reasoning block", () => {
    const h = map("think", "policy")
    expect(h).not.toBeNull()
    expect(h!.trace_index).toBe(1)
    expect(h!.kind).toBe("reasoning")
    expect("Let me think about policy.".slice(h!.start, h!.end)).toBe(
      "think about policy",
    )
  })

  it("maps a span in a tool-call block", () => {
    const h = map("Tool Name", "lookup_policy")
    expect(h).not.toBeNull()
    expect(h!.trace_index).toBe(2)
    expect(h!.kind).toBe("tool_calls")
  })

  it("returns null when the span straddles two blocks", () => {
    // from lands in the user turn, to in the reasoning turn — no single block
    // contains the span, so there is no honest highlight.
    const span = resolve_citation_span(raw_output, {
      from: "What is the return",
      to: "think about",
    })
    expect(span).not.toBeNull()
    expect(map_output_span_to_trace(trace, raw_output, span!)).toBeNull()
  })
})

// ── Calibration loop ──────────────────────────────────────────────────────

function score_traces(
  scores: ("pass" | "fail")[],
): Pick<TraceClaims, "judge_score">[] {
  return scores.map((judge_score) => ({ judge_score }))
}

function rejudge_result(judge_score: "pass" | "fail"): RejudgeCaseResult {
  return {
    judge_score,
    judge_reasoning: `Re-checked: ${judge_score}.`,
    raw_input: "input",
    raw_output: "output",
    trace: null,
  }
}

describe("select_calibration_subset", () => {
  // 16 traces, alternating fail/pass → target floor(16/4) = 4.
  const sixteen = score_traces(
    Array.from({ length: 16 }, (_, i) => (i % 2 === 0 ? "fail" : "pass")),
  )
  const all_judged = sixteen.map((_, i) => i)

  it("fills disagreed first, then flips, then a fresh top-up", () => {
    const subset = select_calibration_subset(sixteen, {
      disagreed: [10],
      flipped: [12, 2],
      reviewed: [10, 11, 12],
      judged: all_judged,
    })
    expect(subset).toHaveLength(4)
    expect(subset).toContain(10)
    expect(subset).toContain(2)
    expect(subset).toContain(12)
    // The remaining slot is a fresh never-reviewed trace.
    const fresh = subset.filter((i) => ![2, 10, 12].includes(i))
    expect(fresh).toHaveLength(1)
    expect([10, 11, 12]).not.toContain(fresh[0])
  })

  it("overflow: disagreed beat flips beat fresh, in stable plan order", () => {
    // 8 traces → target 2; three disagreements overflow the target.
    const eight = score_traces(Array.from({ length: 8 }, () => "pass"))
    expect(
      select_calibration_subset(eight, {
        disagreed: [5, 1, 7],
        flipped: [0, 2],
        reviewed: [1, 5, 7],
        judged: eight.map((_, i) => i),
      }),
    ).toEqual([1, 5])
    // One disagreement + overflowing flips: the flip slot goes to the
    // earliest flipped index.
    expect(
      select_calibration_subset(eight, {
        disagreed: [3],
        flipped: [6, 0, 4],
        reviewed: [3],
        judged: eight.map((_, i) => i),
      }),
    ).toEqual([0, 3])
  })

  it("excludes cases without a fresh verdict from every stratum", () => {
    const eight = score_traces(Array.from({ length: 8 }, () => "pass"))
    const judged = [0, 3, 4, 6, 7] // 1, 2, 5 failed to re-judge
    const subset = select_calibration_subset(eight, {
      disagreed: [1],
      flipped: [2],
      reviewed: [1, 2],
      judged,
    })
    expect(subset).toHaveLength(2)
    for (const i of subset) expect(judged).toContain(i)
  })

  it("tops up fresh picks stratified across pass and fail", () => {
    const subset = select_calibration_subset(sixteen, {
      disagreed: [],
      flipped: [],
      reviewed: [0, 1],
      judged: all_judged,
    })
    expect(subset).toHaveLength(4)
    // Never-reviewed only.
    expect(subset).not.toContain(0)
    expect(subset).not.toContain(1)
    // Both verdict classes present (alternating scores make this checkable).
    const scores = subset.map((i) => sixteen[i].judge_score)
    expect(scores).toContain("fail")
    expect(scores).toContain("pass")
  })

  it("uses the same target math as the first round (floor(N/4), min 1)", () => {
    const three = score_traces(["pass", "fail", "pass"])
    const subset = select_calibration_subset(three, {
      disagreed: [],
      flipped: [],
      reviewed: [],
      judged: [0, 1, 2],
    })
    expect(subset).toHaveLength(1)
  })

  it("returns fewer than target when the eligible pool is smaller", () => {
    const subset = select_calibration_subset(sixteen, {
      disagreed: [2],
      flipped: [],
      reviewed: all_judged,
      judged: [2, 4],
    })
    // Target is 4 but only two traces re-judged, and every trace was
    // already reviewed — no fresh candidates exist.
    expect(subset).toEqual([2])
  })

  it("returns empty when no re-judged trace is eligible (the round-failure trigger)", () => {
    // Disagreed/flipped traces failed to re-judge and every fresh verdict
    // belongs to an already-reviewed trace. The wizard must treat this as a
    // failed round on the retryable surface — a 0-of-0 review would wedge
    // the save gate.
    const eight = score_traces(Array.from({ length: 8 }, () => "pass"))
    expect(
      select_calibration_subset(eight, {
        disagreed: [1],
        flipped: [2],
        reviewed: [0, 3, 4, 5, 6, 7],
        judged: [0, 3, 4],
      }),
    ).toEqual([])
  })
})

describe("calibration_gate_target — save gate during rounds", () => {
  it("keeps the standard target when the round surfaced a full subset", () => {
    expect(calibration_gate_target(40, 10)).toBe(10)
  })

  it("caps the demand at the subset size on a re-judge shortfall", () => {
    // The gate must never demand reviews of traces the round didn't show —
    // otherwise a large shortfall makes the Save CTA unreachable.
    expect(calibration_gate_target(40, 3)).toBe(3)
    expect(calibration_gate_target(40, 1)).toBe(1)
  })

  it("keeps the floor-1 target when the subset covers it", () => {
    expect(calibration_gate_target(3, 3)).toBe(1)
  })

  it("is zero only for the empty subset the wizard never lets reach review", () => {
    expect(calibration_gate_target(40, 0)).toBe(0)
  })
})

describe("flipped_indices", () => {
  it("reports only re-judged cases whose verdict changed", () => {
    const traces = score_traces(["pass", "fail", "pass", "fail"])
    const results = new Map([
      [0, rejudge_result("fail")], // flip
      [1, rejudge_result("fail")], // unchanged
      [3, rejudge_result("pass")], // flip
      // 2 failed to re-judge: unknown, not unchanged — never a flip.
    ])
    expect(flipped_indices(traces, results)).toEqual([0, 3])
  })
})

describe("apply_rejudge_results", () => {
  it("folds fresh verdicts in and resets claims for rebuild", () => {
    const t = trace({ trace_id: "batch_case_0", leaf_run_id: "leaf_0" })
    const applied = apply_rejudge_results(
      [t],
      new Map([[0, rejudge_result("pass")]]),
      "batch_r1",
    )
    expect(applied[0].judge_score).toBe("pass")
    expect(applied[0].judge_reasoning).toBe("Re-checked: pass.")
    expect(applied[0].claims).toBeNull()
    expect(applied[0].final_judgement).toBeNull()
    expect(applied[0].claims_state).toBe("unbuilt")
    // New per-round trace_id: an in-flight claim build from the previous
    // round must miss the identity guard, not corrupt the fresh state.
    expect(applied[0].trace_id).toBe("batch_r1_case_0")
    expect(applied[0].leaf_run_id).toBe("leaf_0")
  })

  it("leaves cases that failed to re-judge untouched", () => {
    const t = trace({ trace_id: "batch_case_0" })
    const applied = apply_rejudge_results([t], new Map(), "batch_r1")
    expect(applied[0]).toEqual(t)
  })

  it("grades reset: reviews rebuilt from the applied traces start empty", () => {
    const t = trace()
    const applied = apply_rejudge_results(
      [t],
      new Map([[0, rejudge_result("pass")]]),
      "batch_r1",
    )
    const reviews = build_trace_reviews(applied)
    expect(reviews[0].final_judgement_verdict.agrees).toBeNull()
    expect(reviews[0].claim_verdicts).toHaveLength(0)
  })
})

describe("plan_save_action — loop entry and exit", () => {
  it("multi-turn with disagreement enters a calibration round", () => {
    expect(
      plan_save_action({ is_multi_turn: true, has_disagreement: true }),
    ).toEqual({ action: "calibrate" })
  })

  it("keeps calibrating however many rounds have run — the loop is uncapped", () => {
    // The planner takes no round count, so nothing about a long-running loop
    // can flip it to save. The only ways out are convergence and the explicit
    // save-without-refining link, which bypasses this planner entirely.
    expect(
      plan_save_action({ is_multi_turn: true, has_disagreement: true }),
    ).toEqual({ action: "calibrate" })
  })

  it("converged reviews save (with the last refined judge)", () => {
    expect(
      plan_save_action({ is_multi_turn: true, has_disagreement: false }),
    ).toEqual({ action: "save" })
  })

  it("single-turn always saves — the loop never runs there", () => {
    expect(
      plan_save_action({ is_multi_turn: false, has_disagreement: true }),
    ).toEqual({ action: "save" })
    expect(
      plan_save_action({ is_multi_turn: false, has_disagreement: false }),
    ).toEqual({ action: "save" })
  })
})

describe("silent_refine_at_save", () => {
  it("multi-turn save never silently refines; single-turn keeps it", () => {
    // Multi-turn ships review_judge untouched: refinement already ran
    // explicitly in the loop and the reviewer graded that judge's verdicts.
    expect(silent_refine_at_save(true)).toBe(false)
    expect(silent_refine_at_save(false)).toBe(true)
  })
})

describe("has_grade_disagreement / disagreed_trace_indices", () => {
  function graded(
    final: "agree" | "disagree",
    claims: ("agree" | "disagree")[] = [],
  ) {
    const graded_claim = (human_grade: "agree" | "disagree") => ({
      claim: "c",
      evidence: "e",
      expected_result: "fail" as const,
      human_grade,
      human_feedback: null,
    })
    return {
      final_judgement: graded_claim(final),
      claims: claims.map(graded_claim),
    }
  }

  it("flags a disagreement on the final judgement or any claim", () => {
    expect(has_grade_disagreement([graded("agree")])).toBe(false)
    expect(has_grade_disagreement([graded("disagree")])).toBe(true)
    expect(
      has_grade_disagreement([graded("agree", ["agree", "disagree"])]),
    ).toBe(true)
  })

  it("finds trace indices carrying any explicit disagree verdict", () => {
    const agree: TraceReview = {
      trace_id: "t0",
      claim_verdicts: [{ agrees: true, why: "" }],
      final_judgement_verdict: { agrees: true, why: "" },
    }
    const final_disagree: TraceReview = {
      trace_id: "t1",
      claim_verdicts: [],
      final_judgement_verdict: { agrees: false, why: "wrong" },
    }
    const claim_disagree: TraceReview = {
      trace_id: "t2",
      claim_verdicts: [{ agrees: false, why: "off" }],
      final_judgement_verdict: { agrees: true, why: "" },
    }
    const unreviewed: TraceReview = {
      trace_id: "t3",
      claim_verdicts: [{ agrees: null, why: "" }],
      final_judgement_verdict: { agrees: null, why: "" },
    }
    expect(
      disagreed_trace_indices([
        agree,
        final_disagree,
        claim_disagree,
        unreviewed,
      ]),
    ).toEqual([1, 2])
  })
})

describe("review_cta — primary action after a review", () => {
  it("offers a refine round whenever disagreements remain", () => {
    expect(review_cta({ num_disagreements: 1 })).toBe("refine")
    expect(review_cta({ num_disagreements: 9 })).toBe("refine")
  })

  it("offers the plain save the moment disagreements clear", () => {
    // Zero disagreements is the convergence signal, whether it's the first
    // pass or the tail of a long refine loop.
    expect(review_cta({ num_disagreements: 0 })).toBe("save")
  })
})

describe("rejudge_shortfall_notice", () => {
  it("silent when every case re-judged", () => {
    expect(rejudge_shortfall_notice(0)).toBeNull()
  })

  it("counts the stale cases honestly, singular and plural", () => {
    expect(rejudge_shortfall_notice(1)).toContain("1 conversation ")
    expect(rejudge_shortfall_notice(3)).toContain("3 conversations ")
    expect(rejudge_shortfall_notice(3)).toContain(
      "left out of this review round",
    )
    expect(rejudge_shortfall_notice(3)).not.toMatch(/—/)
  })
})

describe("review CTA — grade_disagreement_count / refine_judge_tooltip", () => {
  function graded(
    final: "agree" | "disagree",
    claims: ("agree" | "disagree")[] = [],
  ) {
    const graded_claim = (human_grade: "agree" | "disagree") => ({
      claim: "c",
      evidence: "e",
      expected_result: "fail" as const,
      human_grade,
      human_feedback: null,
    })
    return {
      final_judgement: graded_claim(final),
      claims: claims.map(graded_claim),
    }
  }

  it("counts traces carrying a disagreement, matching the loop's predicate", () => {
    // The label flips to Refine Judge exactly when the count is non-zero —
    // the same condition under which a save click starts a refine round.
    expect(grade_disagreement_count([])).toBe(0)
    expect(grade_disagreement_count([graded("agree")])).toBe(0)
    const set = [
      graded("agree"),
      graded("disagree"),
      graded("agree", ["agree", "disagree"]),
    ]
    expect(grade_disagreement_count(set)).toBe(2)
    expect(has_grade_disagreement(set)).toBe(true)
  })

  it("flips back to zero the moment the last disagreement clears", () => {
    // Convergence signal: an all-agree set counts zero, so the CTA returns
    // to the save label reactively.
    expect(
      grade_disagreement_count([graded("agree"), graded("agree", ["agree"])]),
    ).toBe(0)
  })

  it("banner and tooltip share the built-claims count: blind disagreements don't count", () => {
    // A disagreement graded on the blind verdict of a claims-errored trace
    // is excluded by build_graded_traces, so the escape banner, the CTA
    // tooltip, and the loop-entry predicate all see the same number.
    const errored = trace({
      claims_state: "error",
      claims: null,
      final_judgement: null,
      claims_error: "build failed",
    })
    const review: TraceReview = {
      trace_id: "trace_0",
      claim_verdicts: [],
      final_judgement_verdict: { agrees: false, why: "wrong call" },
    }
    const graded_set = build_graded_traces([errored], [review])
    expect(graded_set).toHaveLength(0)
    expect(grade_disagreement_count(graded_set)).toBe(0)
  })

  it("tooltip names the count, singular and plural, without em-dashes", () => {
    expect(refine_judge_tooltip(1)).toContain(
      "disagreed with the judge on 1 conversation.",
    )
    expect(refine_judge_tooltip(3)).toContain(
      "disagreed with the judge on 3 conversations.",
    )
    expect(refine_judge_tooltip(3)).toContain(
      "improve the judge from your feedback and re-check your eval data, then you'll review once more.",
    )
    expect(refine_judge_tooltip(1)).not.toMatch(/—/)
  })
})
