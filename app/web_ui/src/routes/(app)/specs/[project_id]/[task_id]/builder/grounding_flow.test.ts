import { describe, expect, it, vi } from "vitest"
import { KilnError } from "$lib/utils/error_handlers"
import type { OpenEnvReset } from "$lib/types"
import {
  restore_cached_grounded_cases,
  type CachedGroundedCases,
  type SyntheticUserCaseWire,
} from "./builder_draft"
import {
  apply_grounding_frame,
  dropped_notice,
  dropped_notice_drops,
  drops_refine_text,
  drops_action,
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
  single_turn_items_from_cases,
  single_turn_pipeline_inputs,
  ungrounded_single_turn_items,
  plan_row_cases,
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
    input: null,
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
    grounding_model: {
      model_name: "gpt_5_4",
      model_provider: "openai" as const,
    },
    specification: "No fabrication.",
    cases: grounding_request_cases(CASES, PLAN),
  }

  it("sends the guide and example input trimmed", () => {
    expect(
      ground_cases_request({
        ...base,
        data_guide: "  Shoppers asking about orders.\n",
        example_input: " Where is order 12? ",
      }),
    ).toEqual({
      ...base,
      data_guide: "Shoppers asking about orders.",
      example_input: "Where is order 12?",
      max_turns: null,
      rehearsal_judge: null,
    })
  })

  it("sends the multi-turn drive's turn limit", () => {
    expect(
      ground_cases_request({ ...base, data_guide: "", max_turns: 1 }).max_turns,
    ).toBe(1)
  })

  it("sends the rehearsal judge only when one is given", () => {
    const judge = {
      prompt: "Pass when the order is right.",
      model_name: "claude_sonnet_5_5",
      model_provider: "anthropic" as const,
      thinking_level: null,
    }
    expect(
      ground_cases_request({ ...base, data_guide: "", rehearsal_judge: judge })
        .rehearsal_judge,
    ).toEqual(judge)
    expect(
      ground_cases_request({ ...base, data_guide: "" }).rehearsal_judge,
    ).toBeNull()
  })

  it("sends a blank guide and a missing example as null", () => {
    const body = ground_cases_request({ ...base, data_guide: " \n " })
    expect(body.data_guide).toBeNull()
    expect(body.example_input).toBeNull()
  })
})

describe("plan_row_cases and single-turn request cases", () => {
  it("sends each plan row as a scenario with nothing drafted", () => {
    expect(grounding_request_cases(plan_row_cases(PLAN), PLAN, true)).toEqual(
      PLAN.map((scenario, i) => ({ scenario_index: i, scenario })),
    )
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
      rehearsal_score: null,
      rehearsal_reasoning: null,
    })
  })

  it("keeps the rehearsal verdict on a grounded case", () => {
    const frame: GroundingFrame = {
      ...(grounded_frame(1) as Extract<
        GroundingFrame,
        { type: "case_grounded" }
      >),
      rehearsal_score: "fail",
      rehearsal_reasoning: "It changed the wrong order.",
    }
    const state = apply_grounding_frame(
      initial_grounding_state(2),
      frame,
      CASES,
      request,
    )
    expect(state.grounded[1]?.rehearsal_score).toBe("fail")
    expect(state.grounded[1]?.rehearsal_reasoning).toBe(
      "It changed the wrong order.",
    )
  })

  it("keeps a single-turn case's input where the drive reads it", () => {
    const rows = plan_row_cases(PLAN)
    const frame: GroundingFrame = {
      ...(grounded_frame(0) as Extract<
        GroundingFrame,
        { type: "case_grounded" }
      >),
      seed_prompt: null,
      synthetic_user_info: null,
      input: "How many linen sets sold last month?",
    }
    const state = apply_grounding_frame(
      initial_grounding_state(PLAN.length),
      frame,
      rows,
      grounding_request_cases(rows, PLAN, true),
    )
    expect(state.grounded[0]?.seed_prompt).toBe(
      "How many linen sets sold last month?",
    )
    expect(state.grounded[0]?.synthetic_user_info).toBe("")
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
    grounding_model: "openai/gpt_5_4",
    data_guide: "",
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

describe("drops_action", () => {
  it("leads with Continue up to 15% dropped", () => {
    expect(drops_action(0, 20)).toBe("continue_first")
    expect(drops_action(3, 20)).toBe("continue_first")
  })

  it("leads with Refine Plan above 15%", () => {
    expect(drops_action(4, 20)).toBe("refine_first")
    expect(drops_action(9, 20)).toBe("refine_first")
  })

  it("offers only Refine Plan at half or more", () => {
    expect(drops_action(10, 20)).toBe("refine_only")
    expect(drops_action(20, 20)).toBe("refine_only")
  })

  it("treats an empty plan as nothing left to continue with", () => {
    expect(drops_action(0, 0)).toBe("refine_only")
  })
})

describe("dropped_notice", () => {
  it("counts several drops against the plan", () => {
    expect(dropped_notice(2, 20, "conversation")).toBe(
      "2 of 20 planned conversations were dropped when Kiln checked them against your OpenEnv server. Continue with the ones that fit, or refine the plan and generate again.",
    )
  })

  it("reads in the singular for one drop", () => {
    expect(dropped_notice(1, 20, "conversation")).toBe(
      "1 of 20 planned conversations was dropped when Kiln checked it against your OpenEnv server. Continue with the ones that fit, or refine the plan and generate again.",
    )
  })

  it("names inputs on a single-turn build", () => {
    expect(dropped_notice(1, 10, "input")).toBe(
      "1 of 10 planned inputs was dropped when Kiln checked it against your OpenEnv server. Continue with the ones that fit, or refine the plan and generate again.",
    )
  })
})

describe("drops_refine_text", () => {
  it("says none of the plan fit", () => {
    expect(drops_refine_text(20, 20, "conversation")).toBe(
      "None of the 20 planned conversations fit your OpenEnv server. Refine the plan, and Kiln will plan around what didn't fit.",
    )
  })

  it("reads in the singular for a one-item plan", () => {
    expect(drops_refine_text(1, 1, "input")).toBe(
      "The planned input didn't fit your OpenEnv server. Refine the plan, and Kiln will plan around what didn't fit.",
    )
  })

  it("says too many didn't fit when some did", () => {
    expect(drops_refine_text(6, 10, "input")).toBe(
      "6 of 10 planned inputs didn't fit your OpenEnv server, too many for a useful eval. Refine the plan, and Kiln will plan around what didn't fit.",
    )
  })
})

describe("single-turn items", () => {
  const RESET_A = {
    openenv_server_id: "srv",
    reset_kwargs: { fixture: "small" },
  }
  const grounded_case = (seed: string): SyntheticUserCaseWire => ({
    seed_prompt: seed,
    synthetic_user_info: "<persona>p</persona>",
    openenv_reset: RESET_A,
    judge_guidance: `facts for ${seed}`,
  })

  it("runs each grounded case's input in its episode", () => {
    expect(single_turn_items_from_cases([grounded_case("Restock it")])).toEqual(
      [
        {
          input: "Restock it",
          grounding: {
            openenv_reset: RESET_A,
            judge_guidance: "facts for Restock it",
          },
          rehearsal_score: null,
          rehearsal_reasoning: null,
        },
      ],
    )
  })

  it("keeps a case's rehearsal verdict beside its grounding, not in it", () => {
    const [item] = single_turn_items_from_cases([
      {
        ...grounded_case("Restock it"),
        rehearsal_score: "pass",
        rehearsal_reasoning: "Restocked the right item.",
      },
    ])
    expect(item.rehearsal_score).toBe("pass")
    expect(item.rehearsal_reasoning).toBe("Restocked the right item.")
    expect(single_turn_pipeline_inputs([item]).groundings).toEqual([
      { openenv_reset: RESET_A, judge_guidance: "facts for Restock it" },
    ])
  })

  it("refuses a case the grounding stream didn't ground", () => {
    const ungrounded = { ...grounded_case("Restock it"), openenv_reset: null }
    expect(() => single_turn_items_from_cases([ungrounded])).toThrow(
      "Case 0 has no OpenEnv episode to run in.",
    )
  })

  it("sends grounded inputs with their groundings", () => {
    const items = single_turn_items_from_cases([
      grounded_case("A"),
      grounded_case("B"),
    ])
    expect(single_turn_pipeline_inputs(items)).toEqual({
      inputs: ["A", "B"],
      groundings: items.map((item) => item.grounding),
    })
  })

  it("omits groundings when no input is grounded", () => {
    expect(
      single_turn_pipeline_inputs(ungrounded_single_turn_items(["A", "B"])),
    ).toEqual({ inputs: ["A", "B"], groundings: null })
  })

  it("refuses a batch that mixes grounded and ungrounded inputs", () => {
    const items = [
      ...single_turn_items_from_cases([grounded_case("A")]),
      ...ungrounded_single_turn_items(["B"]),
    ]
    expect(() => single_turn_pipeline_inputs(items)).toThrow(
      "Input 1 isn't grounded",
    )
  })
})
