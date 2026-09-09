import { describe, it, expect } from "vitest"
import type { Eval, EvalConfig } from "$lib/types"
import {
  comparable_eval_configs,
  compute_run_disallowed_missing_ref_data,
} from "./judge_comparison_gate"

function make_eval(evaluation_data_type: string | null): Eval {
  return {
    v: 1,
    name: "Test Eval",
    output_scores: [],
    evaluation_data_type,
    model_type: "eval",
  } as unknown as Eval
}

function make_v2_config(
  name: string,
  properties: Record<string, unknown>,
): EvalConfig {
  return {
    v: 1,
    id: name,
    name,
    config_type: "v2",
    properties,
    model_type: "v2",
  } as unknown as EvalConfig
}

function make_v1_config(
  config_type: "g_eval" | "llm_as_judge" = "g_eval",
): EvalConfig {
  return {
    v: 1,
    id: config_type,
    name: config_type,
    config_type,
    properties: { eval_steps: ["step1"] },
    model_type: "legacy",
  } as unknown as EvalConfig
}

const llm_judge = (reference_keys: string[]) => ({
  type: "llm_judge",
  model_name: "gpt-4",
  model_provider: "openai",
  prompt_template: "Grade {{ final_message }}",
  reference_keys,
  g_eval: false,
})

const ordinary_eval = make_eval("final_answer")
const reference_answer_eval = make_eval("reference_answer")

describe("compute_run_disallowed_missing_ref_data", () => {
  it("blocks a V2 judge that declares a reference key", () => {
    expect(
      compute_run_disallowed_missing_ref_data(
        make_v2_config("reference judge", llm_judge(["reference_answer"])),
        ordinary_eval,
      ),
    ).toBe(true)
  })

  it("allows an ordinary V2 judge", () => {
    expect(
      compute_run_disallowed_missing_ref_data(
        make_v2_config("ordinary judge", llm_judge([])),
        ordinary_eval,
      ),
    ).toBe(false)
  })

  it.each([
    ["exact_match", { reference_key: "reference_answer" }, true],
    ["exact_match", { expected_value: "yes" }, false],
    ["contains", { reference_key: "reference_answer" }, true],
    ["contains", { substring: "yes" }, false],
    ["set_check", { reference_key: "reference_answer" }, true],
    ["set_check", { expected_set: ["a"] }, false],
    ["pattern_match", { pattern: "^y" }, false],
    [
      "code_eval",
      { code: "def score():\n  return 1", reference_keys: [] },
      false,
    ],
    [
      "code_eval",
      {
        code: "def score():\n  return 1",
        reference_keys: ["reference_answer"],
      },
      true,
    ],
  ])(
    "reads the reference key(s) declared by a %s judge",
    (type, props, expected) => {
      expect(
        compute_run_disallowed_missing_ref_data(
          make_v2_config(String(type), { type, ...(props as object) }),
          ordinary_eval,
        ),
      ).toBe(expected)
    },
  )

  it("blocks a V1 judge on a reference answer eval", () => {
    expect(
      compute_run_disallowed_missing_ref_data(
        make_v1_config("g_eval"),
        reference_answer_eval,
      ),
    ).toBe(true)
    expect(
      compute_run_disallowed_missing_ref_data(
        make_v1_config("llm_as_judge"),
        reference_answer_eval,
      ),
    ).toBe(true)
  })

  it.each([["final_answer"], ["full_trace"], [null]])(
    "allows a V1 judge on a %s eval, which grades the output on its own",
    (data_type) => {
      expect(
        compute_run_disallowed_missing_ref_data(
          make_v1_config("g_eval"),
          make_eval(data_type),
        ),
      ).toBe(false)
    },
  )

  it("throws rather than guessing for an eval data type it does not know", () => {
    // Pins the exhaustiveness guard: a fourth EvalDataType that needs reference data
    // must not answer "runnable" by falling off the end of the switch.
    expect(() =>
      compute_run_disallowed_missing_ref_data(
        make_v1_config("g_eval"),
        make_eval("invented_data_type"),
      ),
    ).toThrow("Unexpected value")
  })

  it("does not apply the V1 rule to a V2 judge on a reference answer eval", () => {
    // The V2 judge declares what it needs; the eval's data type is the V1 signal only.
    expect(
      compute_run_disallowed_missing_ref_data(
        make_v2_config("ordinary judge", llm_judge([])),
        reference_answer_eval,
      ),
    ).toBe(false)
  })

  it("allows a V2 judge whose properties are an untyped legacy dict", () => {
    expect(
      compute_run_disallowed_missing_ref_data(
        make_v2_config("legacy shaped", { eval_steps: ["step1"] }),
        ordinary_eval,
      ),
    ).toBe(false)
  })
})

describe("comparable_eval_configs", () => {
  it("keeps only the judges judge comparison can score", () => {
    const configs = [
      make_v2_config("ordinary", llm_judge([])),
      make_v2_config("reference", llm_judge(["reference_answer"])),
    ]
    expect(
      comparable_eval_configs(configs, ordinary_eval).map((c) => c.name),
    ).toEqual(["ordinary"])
  })

  it("is empty until both the configs and the eval have loaded", () => {
    expect(comparable_eval_configs(null, ordinary_eval)).toEqual([])
    expect(
      comparable_eval_configs(
        [make_v2_config("ordinary", llm_judge([]))],
        null,
      ),
    ).toEqual([])
  })
})
