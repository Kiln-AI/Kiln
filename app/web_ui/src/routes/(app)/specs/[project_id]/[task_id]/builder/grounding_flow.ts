// Grounding a multi-turn build's planned cases in its OpenEnv server: the
// request the ground_cases stream takes, the frames it sends back, and how
// they fold into the grounded cases and the drops the builder shows.

import type { components } from "$lib/api_schema"
import type { ModelChoice } from "$lib/eval/default_judge"
import type { OpenEnvReset } from "$lib/types"
import { KilnError } from "$lib/utils/error_handlers"
import { sse_data_payloads } from "$lib/utils/sse"
import type { GroundingDrop } from "./batch_plan_guidance"
import type {
  CachedGroundedCases,
  SyntheticUserCaseWire,
} from "./builder_draft"

export type { GroundingDrop } from "./batch_plan_guidance"

export type GroundCaseApi = components["schemas"]["GroundCaseApi"]
export type GroundCasesRequest = components["schemas"]["GroundCasesRequest"]

// The ground_cases stream's frames (eval_builder_models.py). One frame per
// finished case, in finishing order, between grounding_started and
// grounding_finished; grounding_failed ends the stream in place of the last.
export type GroundingFrame =
  | { type: "grounding_started"; total: number }
  | {
      type: "case_grounded"
      case_index: number
      scenario_index: number
      status: "grounded"
      openenv_reset: OpenEnvReset
      seed_prompt: string
      synthetic_user_info: string
      judge_guidance: string
    }
  | {
      type: "case_dropped"
      case_index: number
      scenario_index: number
      drop_reason: string
      drop_detail: string
    }
  | {
      type: "grounding_finished"
      grounded: number
      dropped: number
      usage_complete: boolean
    }
  | {
      type: "grounding_failed"
      code: "openenv_unreachable" | "grounding_error" | "internal_error"
      message: string
    }

export type GroundingProgress = {
  total: number
  checked: number
  dropped: number
}

export type GroundingOutcome = {
  // The cases that fit, in request order, each with its filled-in simulated
  // user, the episode it runs in and its judge guidance.
  grounded: SyntheticUserCaseWire[]
  // The cases that didn't, in request order.
  drops: GroundingDrop[]
}

// The plan row each case was generated from. kiln_server's salvage can drop
// cases, so a case's position need not be its plan row; scenario_index is.
function plan_row(case_wire: SyntheticUserCaseWire, position: number): number {
  return case_wire.scenario_index ?? position
}

// The request's cases: each generated case with the plan text it came from,
// which the grounding agent reads as the scenario to keep testing.
export function grounding_request_cases(
  cases: SyntheticUserCaseWire[],
  plan_prompts: string[],
): GroundCaseApi[] {
  return cases.map((c, i) => {
    const row = plan_row(c, i)
    return {
      scenario_index: row,
      // The route requires a scenario. A case whose row is missing from the
      // plan can't happen with a plan the cases were generated from, and the
      // seed message is the closest stand-in if it ever does.
      scenario: plan_prompts[row]?.trim() || c.seed_prompt,
      seed_prompt: c.seed_prompt,
      synthetic_user_info: c.synthetic_user_info,
    }
  })
}

// The model the grounding agent runs on: the judge model, at the judge's
// thinking level (null runs it at the model's default).
export type GroundingModel = ModelChoice & { thinking_level?: string | null }

// The ground_cases request body. A blank synthetic user guide is sent as
// null, so the grounding agent reads no guide rather than an empty one.
export function ground_cases_request(args: {
  target_run_config_id: string
  judge_model: GroundingModel
  specification: string
  cases: GroundCaseApi[]
  synthetic_user_guide: string
}): GroundCasesRequest {
  return {
    ...args,
    synthetic_user_guide: args.synthetic_user_guide.trim() || null,
  }
}

export type GroundingState = {
  total: number
  grounded: Record<number, SyntheticUserCaseWire>
  drops: Record<number, GroundingDrop>
  finished: boolean
}

export function initial_grounding_state(total: number): GroundingState {
  return { total, grounded: {}, drops: {}, finished: false }
}

// A frame naming a case the request never sent. Ignoring it would shrink the
// batch without a word, so the step fails instead.
function unknown_case(case_index: number): KilnError {
  return new KilnError(
    `Checking cases against your OpenEnv server returned a result for case ${case_index}, which was not sent.`,
  )
}

// Folds one frame into the state. A grounded case keeps everything the drive
// already knows about it, names its plan row as the request resolved it, and
// takes the frame's simulated user, episode and guidance. grounding_failed
// throws: the step fails, and no case is dropped for an error that isn't the
// case's fault.
export function apply_grounding_frame(
  state: GroundingState,
  frame: GroundingFrame,
  cases: SyntheticUserCaseWire[],
  request_cases: GroundCaseApi[],
): GroundingState {
  switch (frame.type) {
    case "grounding_started":
      return { ...state, total: frame.total }
    case "case_grounded": {
      const original = cases[frame.case_index]
      const request_case = request_cases[frame.case_index]
      if (!original || !request_case) throw unknown_case(frame.case_index)
      return {
        ...state,
        grounded: {
          ...state.grounded,
          [frame.case_index]: {
            ...original,
            scenario_index: request_case.scenario_index,
            seed_prompt: frame.seed_prompt,
            synthetic_user_info: frame.synthetic_user_info,
            openenv_reset: frame.openenv_reset,
            judge_guidance: frame.judge_guidance,
          },
        },
      }
    }
    case "case_dropped": {
      const request_case = request_cases[frame.case_index]
      if (!request_case) throw unknown_case(frame.case_index)
      return {
        ...state,
        drops: {
          ...state.drops,
          [frame.case_index]: {
            scenario_index: request_case.scenario_index,
            scenario: request_case.scenario,
            drop_detail: frame.drop_detail,
            drop_reason: frame.drop_reason,
          },
        },
      }
    }
    case "grounding_finished":
      return { ...state, finished: true }
    case "grounding_failed":
      throw new KilnError(frame.message, null, frame.code)
  }
}

export function grounding_progress(state: GroundingState): GroundingProgress {
  const grounded = Object.keys(state.grounded).length
  const dropped = Object.keys(state.drops).length
  return { total: state.total, checked: grounded + dropped, dropped }
}

function in_request_order<T>(by_index: Record<number, T>): T[] {
  return Object.keys(by_index)
    .map(Number)
    .sort((a, b) => a - b)
    .map((i) => by_index[i])
}

export function grounding_outcome(state: GroundingState): GroundingOutcome {
  return {
    grounded: in_request_order(state.grounded),
    drops: in_request_order(state.drops),
  }
}

// Reads the ground_cases stream to its end. A stream that closes without
// grounding_finished (the server went away mid-run) throws rather than
// passing off a partial set as the whole batch.
export async function read_grounding_stream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  args: {
    cases: SyntheticUserCaseWire[]
    request_cases: GroundCaseApi[]
    on_progress: (progress: GroundingProgress) => void
  },
): Promise<GroundingOutcome> {
  let state = initial_grounding_state(args.cases.length)
  for await (const payload of sse_data_payloads(reader)) {
    if (payload === "complete") break
    let frame: GroundingFrame
    try {
      frame = JSON.parse(payload) as GroundingFrame
    } catch {
      continue
    }
    state = apply_grounding_frame(state, frame, args.cases, args.request_cases)
    args.on_progress(grounding_progress(state))
  }
  if (!state.finished) {
    throw new KilnError(
      "Checking cases against your OpenEnv server stopped before it finished.",
    )
  }
  return grounding_outcome(state)
}

// The drops the review's notice lists: those of the grounded set the batch
// under review was driven from, until the notice has been closed once. Null
// when there is nothing to tell.
export function dropped_notice_drops(
  cache: CachedGroundedCases | null,
  driven_prompts_json: string | null,
): GroundingDrop[] | null {
  if (!cache || cache.drops_notice_seen) return null
  if (driven_prompts_json === null) return null
  if (cache.prompts_json !== driven_prompts_json) return null
  return cache.drops.length > 0 ? cache.drops : null
}

// The review's notice, when some planned conversations dropped and the rest
// were driven. planned is the plan's size.
export function dropped_notice(
  dropped: number,
  planned: number,
): { title: string; summary: string } {
  const one = dropped === 1
  return {
    title: one
      ? "A Conversation Was Dropped"
      : "Some Conversations Were Dropped",
    summary: `${dropped} of ${planned} planned conversations ${
      one ? "was" : "were"
    } dropped when Kiln checked ${
      one ? "it" : "them"
    } against your OpenEnv server. ${
      one ? "The row below says" : "Each row says"
    } why. Continue reviewing the conversations that fit, or refine the plan with these reasons in hand.`,
  }
}

// Step 4's message when every planned conversation dropped, so nothing was
// driven.
export function all_dropped_message(planned: number): string {
  return planned === 1
    ? "The planned conversation didn't fit your OpenEnv server. The row below says why."
    : `None of the ${planned} planned conversations fit your OpenEnv server. Each row says why.`
}

// The OpenEnv server a batch's cases were grounded in, or null for an
// ungrounded batch. Every case of a grounded batch names the same server: the
// build has one, and the save refuses cases that disagree with it.
export function grounded_server_id(
  cases: SyntheticUserCaseWire[],
): string | null {
  return (
    cases.find((c) => c.openenv_reset)?.openenv_reset?.openenv_server_id ?? null
  )
}

// A model lane as one string, for keying what depends on the exact model and,
// when one is set, the thinking level it runs at.
export function model_choice_key(
  choice: ModelChoice & { thinking_level?: string | null },
): string {
  const key = `${choice.model_provider}/${choice.model_name}`
  return choice.thinking_level ? `${key}@${choice.thinking_level}` : key
}

// A run config's tool set as one string, order-independent: the OpenEnv
// server lookup depends on which tools there are, not their order.
export function openenv_lookup_key(tool_ids: string[]): string {
  return JSON.stringify([...tool_ids].sort())
}

export type ResetArgumentRow = { path: string; value: string }

// A case's reset arguments as rows to read: nested keys by dotted path
// (`startup.acting_user`), strings as written, anything else as JSON.
export function flatten_reset_arguments(
  reset_kwargs: Record<string, unknown> | null | undefined,
): ResetArgumentRow[] {
  const rows: ResetArgumentRow[] = []
  const walk = (value: unknown, path: string) => {
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).length > 0
    ) {
      for (const [key, child] of Object.entries(value)) {
        walk(child, path ? `${path}.${key}` : key)
      }
      return
    }
    rows.push({
      path,
      value: typeof value === "string" ? value : JSON.stringify(value),
    })
  }
  for (const [key, value] of Object.entries(reset_kwargs ?? {})) {
    walk(value, key)
  }
  return rows
}
