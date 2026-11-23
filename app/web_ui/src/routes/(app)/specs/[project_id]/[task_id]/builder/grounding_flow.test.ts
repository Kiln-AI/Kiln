import { describe, expect, it, vi } from "vitest"
import { KilnError } from "$lib/utils/error_handlers"
import {
  restore_cached_grounded_cases,
  type CachedGroundedCases,
  type SyntheticUserCaseWire,
} from "./builder_draft"
import {
  all_dropped_message,
  apply_grounding_frame,
  dropped_notice,
  dropped_notice_drops,
  flatten_reset_arguments,
  ground_cases_request,
  grounded_server_id,
  grounding_outcome,
  grounding_progress,
  grounding_request_cases,
  initial_grounding_state,
  model_choice_key,
  openenv_lookup_key,
  read_grounding_stream,
  type GroundingFrame,
  type GroundingProgress,
} from "./grounding_flow"

const PLAN = ["Refund a shipped order", "Close an account", "Change a plan"]

// Salvage dropped plan row 1 upstream, so the second case is plan row 2.
const CASES: SyntheticUserCaseWire[] = [
  {
    seed_prompt: "hi",
    synthetic_user_info: "<persona>a</persona>",
    scenario_index: 0,
  },
  {
    seed_prompt: "yo",
    synthetic_user_info: "<persona>b</persona>",
    scenario_index: 2,
  },
]

const RESET = {
  openenv_server_id: "srv_1",
  reset_kwargs: { fixture: "agency" },
}

function grounded_frame(case_index: number): GroundingFrame {
  return {
    type: "case_grounded",
    case_index,
    scenario_index: CASES[case_index]?.scenario_index ?? case_index,
    status: "grounded",
    openenv_reset: RESET,
    seed_prompt: `filled seed ${case_index}`,
    synthetic_user_info: `<persona>filled ${case_index}</persona>`,
    judge_guidance: `## Starting point ${case_index}`,
  }
}

function dropped_frame(case_index: number): GroundingFrame {
  return {
    type: "case_dropped",
    case_index,
    scenario_index: CASES[case_index]?.scenario_index ?? case_index,
    drop_reason: "no_fit",
    drop_detail: "Nothing like it exists.",
  }
}

const FINISHED: GroundingFrame = {
  type: "grounding_finished",
  grounded: 1,
  dropped: 1,
  usage_complete: true,
}

// A reader over SSE text, split into the given chunks so a frame can straddle
// two reads.
function sse_reader(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  }).getReader()
}

function sse(frames: (GroundingFrame | "complete")[]): string {
  return frames
    .map((f) => `data: ${f === "complete" ? f : JSON.stringify(f)}\n\n`)
    .join("")
}

describe("grounding_request_cases", () => {
  it("takes each case's scenario from its own plan row", () => {
    const request = grounding_request_cases(CASES, PLAN)
    expect(request).toEqual([
      {
        scenario_index: 0,
        scenario: "Refund a shipped order",
        seed_prompt: "hi",
        synthetic_user_info: "<persona>a</persona>",
      },
      {
        scenario_index: 2,
        scenario: "Change a plan",
        seed_prompt: "yo",
        synthetic_user_info: "<persona>b</persona>",
      },
    ])
  })

  it("falls back to the case's position without a scenario_index", () => {
    const request = grounding_request_cases(
      [{ seed_prompt: "s", synthetic_user_info: "i" }],
      PLAN,
    )
    expect(request[0]).toMatchObject({
      scenario_index: 0,
      scenario: "Refund a shipped order",
    })
  })

  it("uses the seed message when the plan row is missing", () => {
    const request = grounding_request_cases(
      [{ seed_prompt: "seed", synthetic_user_info: "i", scenario_index: 9 }],
      PLAN,
    )
    expect(request[0].scenario).toBe("seed")
  })
})

describe("ground_cases_request", () => {
  const base = {
    target_run_config_id: "rc_1",
    judge_model: { model_name: "gpt_5_4", model_provider: "openai" as const },
    specification: "No fabrication.",
    cases: grounding_request_cases(CASES, PLAN),
  }

  it("sends the guide trimmed", () => {
    expect(
      ground_cases_request({
        ...base,
        synthetic_user_guide: "  Shoppers asking about orders.\n",
      }),
    ).toEqual({
      ...base,
      synthetic_user_guide: "Shoppers asking about orders.",
    })
  })

  it("sends a blank guide as null", () => {
    expect(
      ground_cases_request({ ...base, synthetic_user_guide: " \n " })
        .synthetic_user_guide,
    ).toBeNull()
    expect(
      ground_cases_request({ ...base, synthetic_user_guide: "" })
        .synthetic_user_guide,
    ).toBeNull()
  })
})

describe("apply_grounding_frame", () => {
  const request = grounding_request_cases(CASES, PLAN)

  it("fills a grounded case and keeps its plan row", () => {
    const state = apply_grounding_frame(
      initial_grounding_state(2),
      grounded_frame(1),
      CASES,
      request,
    )
    expect(state.grounded[1]).toEqual({
      seed_prompt: "filled seed 1",
      synthetic_user_info: "<persona>filled 1</persona>",
      scenario_index: 2,
      openenv_reset: RESET,
      judge_guidance: "## Starting point 1",
    })
  })

  it("names the request's plan row on a grounded case generated without one", () => {
    const unindexed: SyntheticUserCaseWire[] = [
      { seed_prompt: "hi", synthetic_user_info: "<persona>a</persona>" },
    ]
    const state = apply_grounding_frame(
      initial_grounding_state(1),
      grounded_frame(0),
      unindexed,
      grounding_request_cases(unindexed, PLAN),
    )
    expect(state.grounded[0].scenario_index).toBe(0)
  })

  it("records a drop with its plan row, scenario and reason", () => {
    const state = apply_grounding_frame(
      initial_grounding_state(2),
      dropped_frame(1),
      CASES,
      request,
    )
    expect(state.drops[1]).toEqual({
      scenario_index: 2,
      scenario: "Change a plan",
      drop_detail: "Nothing like it exists.",
      drop_reason: "no_fit",
    })
  })

  it("takes the total from grounding_started and marks the end", () => {
    let state = apply_grounding_frame(
      initial_grounding_state(0),
      { type: "grounding_started", total: 2 },
      CASES,
      request,
    )
    expect(state.total).toBe(2)
    state = apply_grounding_frame(state, FINISHED, CASES, request)
    expect(state.finished).toBe(true)
  })

  it("throws on a frame for a case it was not sent", () => {
    const start = initial_grounding_state(2)
    expect(() =>
      apply_grounding_frame(start, grounded_frame(5), CASES, request),
    ).toThrow("case 5, which was not sent")
    expect(() =>
      apply_grounding_frame(start, dropped_frame(5), CASES, request),
    ).toThrow("case 5, which was not sent")
  })

  it("throws the failure with its code", () => {
    const failed = (() => {
      try {
        apply_grounding_frame(
          initial_grounding_state(2),
          {
            type: "grounding_failed",
            code: "openenv_unreachable",
            message: "No OpenEnv server answered at http://127.0.0.1:8000.",
          },
          CASES,
          request,
        )
      } catch (e) {
        return e
      }
    })()
    expect(failed).toBeInstanceOf(KilnError)
    expect((failed as KilnError).getCode()).toBe("openenv_unreachable")
    expect((failed as KilnError).getMessage()).toBe(
      "No OpenEnv server answered at http://127.0.0.1:8000.",
    )
  })
})

describe("grounding progress and outcome", () => {
  it("counts checked and dropped, and returns cases in request order", () => {
    const request = grounding_request_cases(CASES, PLAN)
    let state = initial_grounding_state(2)
    // Finishing order is not request order.
    state = apply_grounding_frame(state, dropped_frame(1), CASES, request)
    state = apply_grounding_frame(state, grounded_frame(0), CASES, request)
    expect(grounding_progress(state)).toEqual({
      total: 2,
      checked: 2,
      dropped: 1,
    })
    const outcome = grounding_outcome(state)
    expect(outcome.grounded.map((c) => c.seed_prompt)).toEqual([
      "filled seed 0",
    ])
    expect(outcome.drops.map((d) => d.scenario)).toEqual(["Change a plan"])
  })
})

describe("read_grounding_stream", () => {
  const request = grounding_request_cases(CASES, PLAN)

  it("reports progress per frame and returns the outcome", async () => {
    const progress: GroundingProgress[] = []
    const text = sse([
      { type: "grounding_started", total: 2 },
      grounded_frame(1),
      dropped_frame(0),
      FINISHED,
      "complete",
    ])
    const outcome = await read_grounding_stream(
      sse_reader([text.slice(0, 40), text.slice(40)]),
      {
        cases: CASES,
        request_cases: request,
        on_progress: (p) => progress.push(p),
      },
    )
    expect(progress.map((p) => p.checked)).toEqual([0, 1, 2, 2])
    expect(progress.at(-1)).toEqual({ total: 2, checked: 2, dropped: 1 })
    expect(outcome.grounded).toHaveLength(1)
    expect(outcome.grounded[0].judge_guidance).toBe("## Starting point 1")
    expect(outcome.drops).toEqual([
      {
        scenario_index: 0,
        scenario: "Refund a shipped order",
        drop_detail: "Nothing like it exists.",
        drop_reason: "no_fit",
      },
    ])
  })

  it("skips a payload that isn't JSON", async () => {
    const text = `data: not json\n\n${sse([FINISHED, "complete"])}`
    const outcome = await read_grounding_stream(sse_reader([text]), {
      cases: CASES,
      request_cases: request,
      on_progress: vi.fn(),
    })
    expect(outcome).toEqual({ grounded: [], drops: [] })
  })

  it("throws when the stream ends without grounding_finished", async () => {
    await expect(
      read_grounding_stream(sse_reader([sse([grounded_frame(0)])]), {
        cases: CASES,
        request_cases: request,
        on_progress: vi.fn(),
      }),
    ).rejects.toThrow("stopped before it finished")
  })

  it("throws a grounding_failed frame", async () => {
    await expect(
      read_grounding_stream(
        sse_reader([
          sse([
            {
              type: "grounding_failed",
              code: "grounding_error",
              message: "The model provider failed.",
            },
          ]),
        ]),
        { cases: CASES, request_cases: request, on_progress: vi.fn() },
      ),
    ).rejects.toThrow("The model provider failed.")
  })
})

describe("grounded_server_id", () => {
  it("names the server the cases' resets start on", () => {
    expect(
      grounded_server_id([
        { ...CASES[0], openenv_reset: RESET, judge_guidance: "g" },
      ]),
    ).toBe("srv_1")
  })

  it("is null for ungrounded cases", () => {
    expect(grounded_server_id(CASES)).toBeNull()
    expect(grounded_server_id([])).toBeNull()
  })
})

describe("keys", () => {
  it("keys a model lane by provider and model", () => {
    expect(
      model_choice_key({ model_name: "gpt_5_4", model_provider: "openai" }),
    ).toBe("openai/gpt_5_4")
  })

  it("keys a thinking level apart, so a new level grounds again", () => {
    const model = { model_name: "gpt_5_4", model_provider: "openai" as const }
    expect(model_choice_key({ ...model, thinking_level: null })).toBe(
      "openai/gpt_5_4",
    )
    expect(model_choice_key({ ...model, thinking_level: "high" })).toBe(
      "openai/gpt_5_4@high",
    )
  })

  it("keys a tool set regardless of order", () => {
    expect(openenv_lookup_key(["b", "a"])).toBe(openenv_lookup_key(["a", "b"]))
    expect(openenv_lookup_key(["a"])).not.toBe(openenv_lookup_key(["a", "b"]))
  })
})

describe("flatten_reset_arguments", () => {
  it("lists nested keys by dotted path, strings as written", () => {
    expect(
      flatten_reset_arguments({
        fixture: "agency",
        seed: 7,
        startup: { acting_user: "u_12", flags: ["a"] },
        setup_sql: "INSERT INTO t VALUES (1);\nINSERT INTO t VALUES (2);",
        empty: {},
        none: null,
      }),
    ).toEqual([
      { path: "fixture", value: "agency" },
      { path: "seed", value: "7" },
      { path: "startup.acting_user", value: "u_12" },
      { path: "startup.flags", value: '["a"]' },
      {
        path: "setup_sql",
        value: "INSERT INTO t VALUES (1);\nINSERT INTO t VALUES (2);",
      },
      { path: "empty", value: "{}" },
      { path: "none", value: "null" },
    ])
  })

  it("is empty without arguments", () => {
    expect(flatten_reset_arguments(undefined)).toEqual([])
    expect(flatten_reset_arguments({})).toEqual([])
  })
})

describe("dropped_notice_drops", () => {
  const plan_json = JSON.stringify(PLAN)
  const drop = {
    scenario_index: 1,
    scenario: "Close an account",
    drop_detail: "Accounts can't be closed.",
  }
  const cache: CachedGroundedCases = {
    prompts_json: plan_json,
    spec_text: "spec",
    openenv_server_id: "srv_1",
    judge_model: "openai/gpt_5_4",
    synthetic_user_guide: "",
    cases: [CASES[0]],
    grounding_dropped: 1,
    drops: [drop],
    drops_notice_seen: false,
  }

  it("lists the drops of the grounded set the review was driven from", () => {
    expect(dropped_notice_drops(cache, plan_json)).toEqual([drop])
  })

  it("is shown once: a seen notice stays closed", () => {
    expect(
      dropped_notice_drops({ ...cache, drops_notice_seen: true }, plan_json),
    ).toBeNull()
  })

  it("stays closed after a reload of a draft that saw it", () => {
    const restored = restore_cached_grounded_cases(
      JSON.parse(JSON.stringify({ ...cache, drops_notice_seen: true })),
    )
    expect(dropped_notice_drops(restored, plan_json)).toBeNull()
  })

  it("still opens after a reload of a draft that hadn't seen it", () => {
    const restored = restore_cached_grounded_cases(
      JSON.parse(JSON.stringify(cache)),
    )
    expect(dropped_notice_drops(restored, plan_json)).toEqual([drop])
  })

  it("says nothing when nothing dropped, or for an older draft's cache", () => {
    expect(dropped_notice_drops({ ...cache, drops: [] }, plan_json)).toBeNull()
    const { drops: _d, drops_notice_seen: _s, ...older } = cache
    expect(
      dropped_notice_drops(restore_cached_grounded_cases(older), plan_json),
    ).toBeNull()
  })

  it("says nothing for a set the batch under review wasn't driven from", () => {
    expect(dropped_notice_drops(cache, JSON.stringify(["other"]))).toBeNull()
    expect(dropped_notice_drops(cache, null)).toBeNull()
    expect(dropped_notice_drops(null, plan_json)).toBeNull()
  })
})

describe("dropped_notice", () => {
  it("counts several drops against the plan", () => {
    expect(dropped_notice(2, 20)).toEqual({
      title: "Some Conversations Were Dropped",
      summary:
        "2 of 20 planned conversations were dropped when Kiln checked them against your OpenEnv server. Continue reviewing the conversations that fit, or refine the plan and generate again.",
    })
  })

  it("reads in the singular for one drop", () => {
    expect(dropped_notice(1, 20)).toEqual({
      title: "A Conversation Was Dropped",
      summary:
        "1 of 20 planned conversations was dropped when Kiln checked it against your OpenEnv server. Continue reviewing the conversations that fit, or refine the plan and generate again.",
    })
  })
})

describe("all_dropped_message", () => {
  it("says none of the planned conversations fit", () => {
    expect(all_dropped_message(20)).toBe(
      "None of the 20 planned conversations fit your OpenEnv server. Each row says why.",
    )
  })

  it("reads in the singular for a one-conversation plan", () => {
    expect(all_dropped_message(1)).toBe(
      "The planned conversation didn't fit your OpenEnv server. The row below says why.",
    )
  })
})
