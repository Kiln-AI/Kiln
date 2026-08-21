import { describe, it, expect } from "vitest"
import type { EvalOutputScore } from "$lib/types"
import { generate_default_code, generate_examples } from "./code_eval_helpers"
import { LLM_JUDGE_TOOL_ID, LLM_TOOL_ID } from "$lib/utils/built_in_tool_ids"

function make_score(
  name: string,
  type: EvalOutputScore["type"],
): EvalOutputScore {
  return { name, type, instruction: null, direction: "higher_is_better" }
}

describe("generate_default_code", () => {
  it("produces a fallback template when output_scores is undefined", () => {
    const code = generate_default_code(undefined)
    expect(code).toContain('"quality"')
    expect(code).toContain("def score(")
    expect(code).toContain('return {"quality": 0.0}')
    expect(code).toContain('return {"quality": 1.0}')
  })

  it("produces a fallback template when output_scores is empty", () => {
    const code = generate_default_code([])
    expect(code).toContain('"quality"')
  })

  describe("single pass_fail score", () => {
    const scores = [make_score("Accuracy", "pass_fail")]

    it("uses json_key for the score name", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('"accuracy"')
      expect(code).not.toContain('"quality"')
    })

    it("documents return 0.0 for Fail or 1.0 for Pass", () => {
      const code = generate_default_code(scores)
      expect(code).toContain("return 0.0 for Fail or 1.0 for Pass")
    })

    it("returns 0.0 for low and 1.0 for passing", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"accuracy": 0.0}')
      expect(code).toContain('{"accuracy": 1.0}')
    })
  })

  describe("single pass_fail_critical score", () => {
    const scores = [make_score("Safety", "pass_fail_critical")]

    it("documents the -1.0/0.0/1.0 range", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        "return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass",
      )
    })

    it("returns 0.0 for low and 1.0 for passing", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"safety": 0.0}')
      expect(code).toContain('{"safety": 1.0}')
    })
  })

  describe("single five_star score", () => {
    const scores = [make_score("Quality", "five_star")]

    it("documents the 1-5 star range", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        "return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)",
      )
    })

    it("uses 1.0 for low (NOT 0.0 which is invalid for five_star)", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"quality": 1.0}')
      expect(code).not.toContain('"quality": 0.0')
    })

    it("uses 5.0 for passing", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"quality": 5.0}')
    })
  })

  describe("multi-output scores", () => {
    const scores = [
      make_score("Accuracy", "pass_fail"),
      make_score("Overall Rating", "five_star"),
      make_score("Safety Check", "pass_fail_critical"),
    ]

    it("builds a bulleted Return dictionary docstring for multiple scores", () => {
      const code = generate_default_code(scores)
      expect(code).toContain("Return dictionary:")
      expect(code).toContain("- accuracy: return 0.0 for Fail or 1.0 for Pass")
      expect(code).toContain(
        "- overall_rating: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)",
      )
      expect(code).toContain(
        "- safety_check: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass",
      )
    })

    it("uses correct per-type low values in the dict", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        '{"accuracy": 0.0, "overall_rating": 1.0, "safety_check": 0.0}',
      )
    })

    it("uses correct per-type passing values in the dict", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        '{"accuracy": 1.0, "overall_rating": 5.0, "safety_check": 1.0}',
      )
    })

    it("contains all json_keys in the return dicts", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('"accuracy"')
      expect(code).toContain('"overall_rating"')
      expect(code).toContain('"safety_check"')
    })
  })

  it("preserves the function signature and Args docstring", () => {
    const scores = [make_score("Test", "pass_fail")]
    const code = generate_default_code(scores)
    expect(code).toContain("def score(output, trace, task_input):")
    expect(code).toContain("Args:")
    expect(code).toContain("output: The model's final output string.")
    expect(code).not.toContain("kiln:")
  })

  it("omits reference data from the signature and docstring", () => {
    const code = generate_default_code([make_score("Test", "pass_fail")])
    expect(code).not.toContain("reference_data")
    expect(generate_default_code(undefined)).not.toContain("reference_data")
  })

  it("includes the optional-params docstring note in the default template", () => {
    const code = generate_default_code(undefined)
    expect(code).toContain("Parameters are optional and order-independent")
  })

  describe("custom score type", () => {
    it("describes custom as an unbounded metric, not pass/fail", () => {
      const scores = [make_score("Custom Score", "custom")]
      const code = generate_default_code(scores)
      expect(code).toContain('"custom_score": 0.0')
      expect(code).toContain(
        "return the metric's value (any finite number, e.g. a count or cost)",
      )
      expect(code).not.toContain("return 0.0 for Fail or 1.0 for Pass")
    })
  })
})

describe("generate_examples", () => {
<<<<<<< HEAD
  // The first three examples are score-key-driven (built via the helper
  // functions); the last two are hand-written LLM tool examples validated
  // separately below.
  const code_examples = (scores?: EvalOutputScore[]) =>
    generate_examples(scores).slice(0, 3)

  it("returns five examples with correct labels", () => {
    const examples = generate_examples(undefined)
    expect(examples).toHaveLength(5)
    expect(examples[0].label).toBe("Parse JSON")
    expect(examples[1].label).toBe("Check tool usage")
    expect(examples[2].label).toBe("Domain-specific grading")
    expect(examples[3].label).toBe("LLM judge")
    expect(examples[4].label).toBe("Triage then LLM judge")
=======
  // The first two examples are score-key-driven (built via the helper
  // functions); the last two are hand-written LLM tool examples validated
  // separately below.
  const code_examples = (scores?: EvalOutputScore[]) =>
    generate_examples(scores).slice(0, 2)

  it("returns four examples with correct labels", () => {
    const examples = generate_examples(undefined)
    expect(examples).toHaveLength(4)
    expect(examples[0].label).toBe("Parse JSON")
    expect(examples[1].label).toBe("Check tool usage")
    expect(examples[2].label).toBe("LLM judge")
    expect(examples[3].label).toBe("Triage then LLM judge")
>>>>>>> 721c4941b
  })

  it("falls back to quality key when no output_scores", () => {
    for (const ex of code_examples(undefined)) {
      expect(ex.code).toContain('"quality"')
    }
  })

  it("omits reference data from every example", () => {
    const scores = [
      make_score("Accuracy", "pass_fail"),
      make_score("Overall Rating", "five_star"),
    ]
    for (const output_scores of [undefined, [], scores]) {
      for (const ex of generate_examples(output_scores)) {
        expect(ex.code).not.toContain("reference_data")
      }
    }
  })

  it("falls back to quality key when output_scores is empty", () => {
    for (const ex of code_examples([])) {
      expect(ex.code).toContain('"quality"')
    }
  })

  it("uses string_to_json_key-derived keys from output_scores", () => {
    const scores = [
      make_score("Valid JSON", "pass_fail"),
      make_score("Overall Rating", "five_star"),
    ]
    for (const ex of code_examples(scores)) {
      expect(ex.code).toContain('"valid_json"')
      expect(ex.code).toContain('"overall_rating"')
    }
  })

  describe("LLM tool examples", () => {
    it("LLM judge example judges the response itself", () => {
<<<<<<< HEAD
      const example = generate_examples(undefined)[3]
=======
      const example = generate_examples(undefined)[2]
>>>>>>> 721c4941b
      expect(example.label).toBe("LLM judge")
      expect(example.code).toContain("from kiln import tools")
      expect(example.code).toContain("tools.llm_judge(")
      expect(example.code).toContain("return json.loads(")
      // Judges the model's own output (not the user's messages).
      expect(example.code).toContain("def score(output):")
      expect(example.code).toContain('input={"response": output}')
    })

    it("Triage example composes tools.llm and tools.llm_judge", () => {
<<<<<<< HEAD
      const example = generate_examples(undefined)[4]
=======
      const example = generate_examples(undefined)[3]
>>>>>>> 721c4941b
      expect(example.label).toBe("Triage then LLM judge")
      expect(example.code).toContain("tools.llm(")
      expect(example.code).toContain("tools.llm_judge(")
      // Cheap triage decides whether the careful judge is even needed.
      expect(example.code).toContain('"needs_review"')
      expect(example.code).toContain("if not triage[")
      // Safe branch threads the eval's score keys via build_return_dict.
      expect(example.code).toContain('return {"quality": 1.0}')
    })

    it("Triage safe-branch uses real score keys from output_scores", () => {
      const scores = [
        make_score("Check", "pass_fail"),
        make_score("Rating", "five_star"),
      ]
<<<<<<< HEAD
      const example = generate_examples(scores)[4]
=======
      const example = generate_examples(scores)[3]
>>>>>>> 721c4941b
      expect(example.code).toContain('return {"check": 1.0, "rating": 5.0}')
    })
  })

  describe("type-appropriate value mapping", () => {
    const scores = [
      make_score("Check", "pass_fail"),
      make_score("Rating", "five_star"),
    ]

    it("uses KilnEvalHelpers.pass_fail for pass_fail scores", () => {
      for (const ex of code_examples(scores)) {
        expect(ex.code).toContain('"check": KilnEvalHelpers.pass_fail(')
      }
    })

    it("uses KilnEvalHelpers.five_star for five_star scores", () => {
      for (const ex of code_examples(scores)) {
        expect(ex.code).toContain('"rating": KilnEvalHelpers.five_star(')
      }
    })

    it("uses KilnEvalHelpers.pass_fail for pass_fail_critical scores", () => {
      const scores_pfc = [make_score("Safety", "pass_fail_critical")]
      for (const ex of code_examples(scores_pfc)) {
        expect(ex.code).toContain('"safety": KilnEvalHelpers.pass_fail(')
      }
    })
  })

  describe("Parse JSON example", () => {
    it("computes passed from isinstance and has_all", () => {
      const examples = generate_examples(undefined)
      expect(examples[0].code).toContain(
        "passed = isinstance(data, dict) and has_all",
      )
    })

    it("uses passed as the bool expression", () => {
      const examples = generate_examples(undefined)
      expect(examples[0].code).toContain("KilnEvalHelpers.pass_fail(passed)")
    })

    it("returns error dict on parse failure with low values", () => {
      const scores = [
        make_score("A", "pass_fail"),
        make_score("B", "five_star"),
      ]
      const examples = generate_examples(scores)
      expect(examples[0].code).toContain('"a": 0.0')
      expect(examples[0].code).toContain('"b": 1.0')
    })
  })

  describe("Check tool usage example", () => {
    it("clamps five_star lower bound to 1 when a five_star score is present", () => {
      const scores = [make_score("Rating", "five_star")]
      const examples = generate_examples(scores)
      expect(examples[1].code).toContain("max(min(call_count, 5), 1)")
    })

    it("uses used_search as the bool expression", () => {
      const examples = generate_examples(undefined)
      expect(examples[1].code).toContain(
        "KilnEvalHelpers.pass_fail(used_search)",
      )
    })
  })

  describe("single score (no multi-line return dict)", () => {
    it("produces inline return for a single score", () => {
      const scores = [make_score("Quality", "pass_fail")]
      const examples = generate_examples(scores)
      expect(examples[1].code).toContain(
        'return {"quality": KilnEvalHelpers.pass_fail(used_search)}',
      )
    })

    it("does not include the adjust comment for a single score", () => {
      const scores = [make_score("Quality", "pass_fail")]
      const examples = generate_examples(scores)
      for (const ex of examples) {
        expect(ex.code).not.toContain("Adjust each")
      }
    })
  })

  describe("multi-score adjust comment", () => {
    it("includes an adjust comment in multi-score return dicts", () => {
      const scores = [
        make_score("Check", "pass_fail"),
        make_score("Rating", "five_star"),
      ]
      for (const ex of code_examples(scores)) {
        expect(ex.code).toContain("# Adjust each score's logic for your eval")
      }
    })
  })
})

describe("example tool requirements", () => {
  // `from kiln import tools` then `tools.<name>(...)`. Anchored on the `tools.`
  // receiver so KilnEvalHelpers.* calls are not mistaken for tool calls, and
  // requiring the open paren so the bare import line does not match.
  const TOOL_CALL_RE = /\btools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(/g

  const TOOL_ID_BY_FUNCTION_NAME: Record<string, string> = {
    llm: LLM_TOOL_ID,
    llm_judge: LLM_JUDGE_TOOL_ID,
  }

  function tool_ids_called_by(code: string): string[] {
    const ids = new Set<string>()
    for (const match of code.matchAll(TOOL_CALL_RE)) {
      const tool_id = TOOL_ID_BY_FUNCTION_NAME[match[1]]
      expect(
        tool_id,
        `example calls tools.${match[1]}, which this test cannot map to a tool ID`,
      ).toBeTruthy()
      ids.add(tool_id)
    }
    return [...ids]
  }

  it("declares every tool its code calls", () => {
    // A code judge may only call tools in its allowlist, and use_example() grants
    // exactly required_tool_ids — so an under-declared example ships code that is
    // rejected the moment the user runs it.
    for (const example of generate_examples()) {
      for (const tool_id of tool_ids_called_by(example.code)) {
        expect(
          example.required_tool_ids,
          `example "${example.label}" calls ${tool_id} without declaring it`,
        ).toContain(tool_id)
      }
    }
  })

  it("finds the LLM examples' calls, so the scan above is not vacuous", () => {
    const called_by_label = Object.fromEntries(
      generate_examples().map((e) => [e.label, tool_ids_called_by(e.code)]),
    )
    expect(called_by_label["LLM judge"]).toEqual([LLM_JUDGE_TOOL_ID])
    expect(called_by_label["Triage then LLM judge"].sort()).toEqual(
      [LLM_TOOL_ID, LLM_JUDGE_TOOL_ID].sort(),
    )
  })

  it("declares nothing for examples that call no tools", () => {
    for (const example of generate_examples()) {
      if (tool_ids_called_by(example.code).length === 0) {
        expect(
          example.required_tool_ids,
          `example "${example.label}" declares tools its code never calls`,
        ).toEqual([])
      }
    }
  })
})
