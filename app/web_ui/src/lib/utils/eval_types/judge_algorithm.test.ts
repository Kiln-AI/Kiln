import { describe, it, expect } from "vitest"
import {
  default_judge_algorithm,
  judge_algorithm_for_model,
  judge_algorithm_request_flags,
  unsupported_judge_algorithms,
  type JudgeAlgorithm,
} from "./judge_algorithm"

function model(supports_logprobs: boolean, supports_function_calling: boolean) {
  return { supports_logprobs, supports_function_calling }
}

const G_EVAL_REASON =
  "G-Eval requires logprobs which do not work with this model or provider."
const AGENTIC_REASON =
  "Agentic Judge requires tool calling, which this model doesn't support."

describe("unsupported_judge_algorithms", () => {
  it.each([
    [true, true, {}],
    [true, false, { agentic_judge: AGENTIC_REASON }],
    [false, true, { g_eval: G_EVAL_REASON }],
    [false, false, { g_eval: G_EVAL_REASON, agentic_judge: AGENTIC_REASON }],
  ])(
    "logprobs=%s, tool calling=%s",
    (supports_logprobs, supports_function_calling, expected) => {
      expect(
        unsupported_judge_algorithms(
          model(supports_logprobs, supports_function_calling),
        ),
      ).toEqual(expected)
    },
  )

  it("always supports LLM as Judge", () => {
    expect(
      unsupported_judge_algorithms(model(false, false)).llm_as_judge,
    ).toBeUndefined()
  })
})

describe("default_judge_algorithm", () => {
  it.each([
    [true, true, "g_eval"],
    [true, false, "g_eval"],
    [false, true, "llm_as_judge"],
    [false, false, "llm_as_judge"],
  ])(
    "logprobs=%s, tool calling=%s gives %s",
    (supports_logprobs, supports_function_calling, expected) => {
      expect(
        default_judge_algorithm(
          model(supports_logprobs, supports_function_calling),
        ),
      ).toBe(expected)
    },
  )
})

describe("judge_algorithm_for_model", () => {
  it("gives the default when nothing was chosen", () => {
    expect(judge_algorithm_for_model(undefined, model(true, true))).toBe(
      "g_eval",
    )
    expect(judge_algorithm_for_model(undefined, model(false, true))).toBe(
      "llm_as_judge",
    )
  })

  it.each<[JudgeAlgorithm, boolean, boolean]>([
    ["agentic_judge", true, true],
    ["agentic_judge", false, true],
    ["llm_as_judge", true, true],
    ["g_eval", true, false],
  ])(
    "keeps a chosen %s while the model supports it",
    (chosen, supports_logprobs, supports_function_calling) => {
      expect(
        judge_algorithm_for_model(
          chosen,
          model(supports_logprobs, supports_function_calling),
        ),
      ).toBe(chosen)
    },
  )

  it.each<[JudgeAlgorithm, boolean, boolean, JudgeAlgorithm]>([
    ["agentic_judge", true, false, "g_eval"],
    ["agentic_judge", false, false, "llm_as_judge"],
    ["g_eval", false, true, "llm_as_judge"],
  ])(
    "falls back from a chosen %s when the model can't run it",
    (chosen, supports_logprobs, supports_function_calling, expected) => {
      expect(
        judge_algorithm_for_model(
          chosen,
          model(supports_logprobs, supports_function_calling),
        ),
      ).toBe(expected)
    },
  )
})

describe("judge_algorithm_request_flags", () => {
  it.each<[JudgeAlgorithm, { g_eval: boolean; trace_tools: boolean }]>([
    ["llm_as_judge", { g_eval: false, trace_tools: false }],
    ["g_eval", { g_eval: true, trace_tools: false }],
    ["agentic_judge", { g_eval: false, trace_tools: true }],
  ])("%s", (algo, expected) => {
    expect(judge_algorithm_request_flags(algo)).toEqual(expected)
  })
})
