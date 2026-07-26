import { describe, expect, it } from "vitest"
import {
  all_traces_reviewed,
  build_claim_review_payload,
  build_graded_traces,
  build_trace_reviews,
  disagreement_feedback,
  is_trace_reviewed,
  MAX_JUDGE_PROMPT_CHARS,
  resolve_citation_span,
  user_says_meets_spec,
  validate_refined_judge_prompt,
  type Claim,
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

  it("anchors to final_judgement.expected_result", () => {
    expect(user_says_meets_spec(trace(), reviewed(true))).toBe(false)
    const passing = trace({
      final_judgement: claim({ expected_result: "pass" }),
    })
    expect(user_says_meets_spec(passing, reviewed(true))).toBe(true)
  })

  it("flips the verdict when the human disagrees with the final judgement", () => {
    expect(user_says_meets_spec(trace(), reviewed(false))).toBe(true)
    const passing = trace({
      final_judgement: claim({ expected_result: "pass" }),
    })
    expect(user_says_meets_spec(passing, reviewed(false))).toBe(false)
  })
})

describe("build_claim_review_payload", () => {
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
