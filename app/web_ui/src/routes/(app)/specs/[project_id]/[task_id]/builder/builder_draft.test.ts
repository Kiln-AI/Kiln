import { afterEach, describe, expect, it } from "vitest"
import {
  builder_draft_key,
  builder_mock_active,
  create_eval_button_label,
  draft_has_content,
  reset_draft_keeping_tags,
  restore_step,
  reusable_cached_cases,
  EMPTY_BUILDER_DRAFT,
  type BuilderDraft,
  type CachedSuCases,
} from "./builder_draft"

// A draft with every field populated — the round-trip and resolution
// fixtures below carve it down.
const full_draft: BuilderDraft = {
  description: "The agent must not fabricate policies.",
  spec_type: "issue",
  name: "no-fabrication",
  property_values: {
    issue_description: "The agent must not fabricate policies.",
    issue_examples: "Invented a 90-day return window.",
    non_issue_examples: null,
  },
  refined_property_values: {
    issue_description: "The agent must not fabricate or guess at policies.",
  },
  suggested_edits: {
    issue_description: {
      proposed_value: "The agent must not fabricate or guess at policies.",
      reason_for_edit: "Broadened to cover guessing.",
    },
  },
  not_incorporated_feedback: "Tone feedback was out of scope.",
  batch_plan: {
    prompts: ["Customer asks about a return window.", "Warranty question."],
    summary: "Two fabrication-bait scenarios.",
  },
  batch_plan_edited: true,
  cached_su_cases: {
    prompts_json: JSON.stringify([
      "Customer asks about a return window.",
      "Warranty question.",
    ]),
    spec_text: "The agent must not fabricate or guess at policies.",
    cases: [
      {
        seed_prompt: "What's your return window?",
        synthetic_user_info: "<persona>impatient</persona>",
        scenario_index: 0,
      },
      {
        seed_prompt: "Is my laptop still under warranty?",
        synthetic_user_info: "<persona>polite</persona>",
        scenario_index: 1,
      },
    ],
  },
  multi_turn_batch_tag: "multi_turn_batch_1234",
  undeleted_batch_tags: ["multi_turn_batch_1200", "multi_turn_batch_1234"],
  su_driver: {
    model_name: "gpt_5_4_mini",
    model_provider: "openai",
  },
  judge_model: {
    model_name: "gpt_5_4",
    model_provider: "openai",
  },
}

describe("draft round-trip", () => {
  it("survives serialization with every field intact", () => {
    // IndexedDB structured-clones the draft; JSON is a strictly harsher
    // proxy (drops functions/undefined), so surviving it guarantees the
    // stored shape restores exactly.
    const restored = JSON.parse(JSON.stringify(full_draft)) as BuilderDraft
    expect(restored).toEqual(full_draft)
    expect(restore_step(restored)).toBe(restore_step(full_draft))
  })

  it("empty draft round-trips to no-content", () => {
    const restored = JSON.parse(
      JSON.stringify(EMPTY_BUILDER_DRAFT),
    ) as BuilderDraft
    expect(restored).toEqual(EMPTY_BUILDER_DRAFT)
    expect(draft_has_content(restored)).toBe(false)
  })

  it("keys drafts per task", () => {
    expect(builder_draft_key("p1", "t1")).not.toBe(
      builder_draft_key("p1", "t2"),
    )
    expect(builder_draft_key("p1", "t1")).toBe(builder_draft_key("p1", "t1"))
  })
})

describe("restore_step resolution", () => {
  it("empty draft restores to describe", () => {
    expect(restore_step(EMPTY_BUILDER_DRAFT)).toBe("describe")
  })

  it("description alone restores to describe (clarify is never a target)", () => {
    expect(
      restore_step({
        ...EMPTY_BUILDER_DRAFT,
        description: "Some spec",
        property_values: { issue_description: "Some spec" },
      }),
    ).toBe("describe")
  })

  it("refined content restores to refine", () => {
    expect(
      restore_step({
        ...EMPTY_BUILDER_DRAFT,
        description: "Some spec",
        refined_property_values: { issue_description: "Refined spec" },
      }),
    ).toBe("refine")
  })

  it("suggested edits alone restore to refine", () => {
    expect(
      restore_step({
        ...EMPTY_BUILDER_DRAFT,
        suggested_edits: {
          issue_description: { proposed_value: "x", reason_for_edit: "" },
        },
      }),
    ).toBe("refine")
  })

  it("whitespace-only refined values do not count as refine content", () => {
    expect(
      restore_step({
        ...EMPTY_BUILDER_DRAFT,
        description: "Some spec",
        refined_property_values: { issue_description: "   " },
      }),
    ).toBe("describe")
  })

  it("a plan restores to the plan screen", () => {
    expect(restore_step(full_draft)).toBe("generate")
  })

  it("never restores past step 4", () => {
    // Even a draft that carries batch tags (a drive happened) resolves to
    // the plan screen at furthest — review state is never persisted.
    expect(["describe", "refine", "generate"]).toContain(
      restore_step(full_draft),
    )
  })

  it("a plan with no prompts falls back to the earlier steps", () => {
    expect(
      restore_step({
        ...full_draft,
        batch_plan: { prompts: [], summary: "" },
      }),
    ).toBe("refine")
  })
})

describe("draft_has_content", () => {
  it("is false for the empty draft", () => {
    expect(draft_has_content(EMPTY_BUILDER_DRAFT)).toBe(false)
  })

  it("is false for whitespace-only fields", () => {
    expect(
      draft_has_content({
        ...EMPTY_BUILDER_DRAFT,
        description: "   ",
        property_values: { issue_description: "  ", other: null },
      }),
    ).toBe(false)
  })

  it("is true for a description", () => {
    expect(
      draft_has_content({ ...EMPTY_BUILDER_DRAFT, description: "spec" }),
    ).toBe(true)
  })

  it("is true for batch tags alone — the orphaned-chain correctness carry", () => {
    // Tags name chains already on disk; a draft carrying only them must
    // still restore so the next drive can clean those chains up.
    expect(
      draft_has_content({
        ...EMPTY_BUILDER_DRAFT,
        undeleted_batch_tags: ["multi_turn_batch_1200"],
      }),
    ).toBe(true)
    expect(
      draft_has_content({
        ...EMPTY_BUILDER_DRAFT,
        multi_turn_batch_tag: "multi_turn_batch_1234",
      }),
    ).toBe(true)
  })

  it("is true for a plan", () => {
    expect(
      draft_has_content({
        ...EMPTY_BUILDER_DRAFT,
        batch_plan: { prompts: ["p"], summary: "s" },
      }),
    ).toBe(true)
  })
})

describe("builder_mock_active — the mock gate", () => {
  afterEach(() => {
    delete (globalThis as { window?: unknown }).window
  })

  it("is false when no window exists (SSR / plain node)", () => {
    expect(builder_mock_active()).toBe(false)
  })

  it("is false in a browser without the mock installed", () => {
    ;(globalThis as { window?: unknown }).window = {}
    expect(builder_mock_active()).toBe(false)
  })

  it("is true once the mock marks the window", () => {
    ;(globalThis as { window?: unknown }).window = {
      __KILN_BUILDER_MOCK_ACTIVE__: true,
    }
    expect(builder_mock_active()).toBe(true)
  })
})

describe("reusable_cached_cases — SU-case reuse", () => {
  const prompts = ["scenario a", "scenario b"]
  const spec = "no fabrication"
  const cache: CachedSuCases = {
    prompts_json: JSON.stringify(prompts),
    spec_text: spec,
    cases: [
      { seed_prompt: "hi", synthetic_user_info: "<persona>x</persona>" },
      { seed_prompt: "yo", synthetic_user_info: "<persona>y</persona>" },
    ],
  }

  it("reuses when plan and spec are byte-unchanged", () => {
    expect(
      reusable_cached_cases(cache, ["scenario a", "scenario b"], spec),
    ).toBe(cache.cases)
  })

  it("misses with no cache", () => {
    expect(reusable_cached_cases(null, prompts, spec)).toBeNull()
  })

  it("misses when a prompt was edited", () => {
    expect(
      reusable_cached_cases(cache, ["scenario a EDITED", "scenario b"], spec),
    ).toBeNull()
  })

  it("misses when a prompt was deleted", () => {
    expect(reusable_cached_cases(cache, ["scenario a"], spec)).toBeNull()
  })

  it("misses when the spec text changed", () => {
    expect(reusable_cached_cases(cache, prompts, "different spec")).toBeNull()
  })

  it("misses on an empty cached case list", () => {
    expect(
      reusable_cached_cases({ ...cache, cases: [] }, prompts, spec),
    ).toBeNull()
  })

  it("prompt order matters (case i maps to prompt i)", () => {
    expect(
      reusable_cached_cases(cache, ["scenario b", "scenario a"], spec),
    ).toBeNull()
  })
})

describe("reset_draft_keeping_tags", () => {
  it("wipes all authoring state but carries the batch tags", () => {
    const fresh = reset_draft_keeping_tags(full_draft)
    expect(fresh.multi_turn_batch_tag).toBe("multi_turn_batch_1234")
    expect(fresh.undeleted_batch_tags).toEqual([
      "multi_turn_batch_1200",
      "multi_turn_batch_1234",
    ])
    expect(fresh.description).toBe("")
    expect(fresh.name).toBe("")
    expect(fresh.batch_plan).toBeNull()
    expect(fresh.cached_su_cases).toBeNull()
    expect(fresh.refined_property_values).toEqual({})
  })

  it("resolves to the describe step after reset", () => {
    expect(restore_step(reset_draft_keeping_tags(full_draft))).toBe("describe")
  })

  it("still counts as content when tags exist, so cleanup survives another restore", () => {
    expect(draft_has_content(reset_draft_keeping_tags(full_draft))).toBe(true)
  })

  it("is a full empty draft when there were no tags", () => {
    const no_tags = {
      ...full_draft,
      multi_turn_batch_tag: null,
      undeleted_batch_tags: [],
    }
    expect(reset_draft_keeping_tags(no_tags)).toEqual(EMPTY_BUILDER_DRAFT)
  })
})

describe("create_eval_button_label", () => {
  it("advertises the draft only with copilot AND content", () => {
    expect(create_eval_button_label(true, true)).toBe("Continue Eval Draft")
    expect(create_eval_button_label(true, false)).toBe("Create Eval")
    expect(create_eval_button_label(false, true)).toBe("Create Eval")
    expect(create_eval_button_label(false, false)).toBe("Create Eval")
  })
})

describe("model lanes (su_driver / judge_model)", () => {
  it("round-trip through serialization", () => {
    const restored = JSON.parse(JSON.stringify(full_draft)) as BuilderDraft
    expect(restored.su_driver).toEqual({
      model_name: "gpt_5_4_mini",
      model_provider: "openai",
    })
    expect(restored.judge_model).toEqual({
      model_name: "gpt_5_4",
      model_provider: "openai",
    })
  })

  it("a pre-Drive-Settings draft restores lanes as null via ??", () => {
    // Drafts written before the lanes existed have no such keys. The
    // builder restores with `saved.su_driver ?? null` — mirror that here
    // against a legacy-shaped blob.
    const { su_driver: _su, judge_model: _judge, ...legacy } = full_draft
    const restored = JSON.parse(JSON.stringify(legacy)) as BuilderDraft
    expect(restored.su_driver ?? null).toBeNull()
    expect(restored.judge_model ?? null).toBeNull()
  })

  it("reset wipes the lanes — pre-population re-fills them", () => {
    const reset = reset_draft_keeping_tags(full_draft)
    expect(reset.su_driver).toBeNull()
    expect(reset.judge_model).toBeNull()
  })

  it("lanes alone do not make a draft restorable", () => {
    expect(
      draft_has_content({
        ...EMPTY_BUILDER_DRAFT,
        su_driver: { model_name: "m", model_provider: "p" },
      }),
    ).toBe(false)
  })
})
