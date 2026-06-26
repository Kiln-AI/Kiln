import { describe, it, expect } from "vitest"
import type { EvalConfig } from "$lib/types"
import {
  evalTypeJudgeLabel,
  evalConfigTypeLabel,
  evalConfigDetailsSummary,
} from "./eval_config_summary"
import type { V2EvalType } from "./registry"

// Helper to build a minimal EvalConfig for testing
function makeV2Config(
  type: string,
  properties: Record<string, unknown>,
): EvalConfig {
  return {
    v: 1,
    name: "test",
    config_type: "v2",
    properties: { type, ...properties },
    model_type: "v2",
  }
}

function makeLegacyConfig(
  configType: "g_eval" | "llm_as_judge",
  properties?: Record<string, unknown>,
): EvalConfig {
  return {
    v: 1,
    name: "test",
    config_type: configType,
    properties: properties ?? null,
    model_type: "legacy",
  }
}

describe("evalTypeJudgeLabel", () => {
  it('returns "LLM as Judge" for llm_judge (no double Judge)', () => {
    expect(evalTypeJudgeLabel("llm_judge")).toBe("LLM as Judge")
  })

  it('returns "Code Judge" for code_eval', () => {
    expect(evalTypeJudgeLabel("code_eval")).toBe("Code Judge")
  })

  it('returns "Exact Match Judge" for exact_match', () => {
    expect(evalTypeJudgeLabel("exact_match")).toBe("Exact Match Judge")
  })

  it('returns "Pattern Match Judge" for pattern_match', () => {
    expect(evalTypeJudgeLabel("pattern_match")).toBe("Pattern Match Judge")
  })

  it('returns "Contains Judge" for contains', () => {
    expect(evalTypeJudgeLabel("contains")).toBe("Contains Judge")
  })

  it('returns "Set Check Judge" for set_check', () => {
    expect(evalTypeJudgeLabel("set_check")).toBe("Set Check Judge")
  })

  it('returns "Tool Call Check Judge" for tool_call_check', () => {
    expect(evalTypeJudgeLabel("tool_call_check")).toBe("Tool Call Check Judge")
  })

  it('returns "Step Count Check Judge" for step_count_check', () => {
    expect(evalTypeJudgeLabel("step_count_check")).toBe(
      "Step Count Check Judge",
    )
  })
})

describe("evalConfigTypeLabel", () => {
  it("returns judge label for V2 config", () => {
    const config = makeV2Config("exact_match", {})
    expect(evalConfigTypeLabel(config)).toBe("Exact Match Judge")
  })

  it('returns "G-Eval" for g_eval legacy config', () => {
    const config = makeLegacyConfig("g_eval")
    expect(evalConfigTypeLabel(config)).toBe("G-Eval")
  })

  it('returns "LLM as Judge" for llm_as_judge legacy config', () => {
    const config = makeLegacyConfig("llm_as_judge")
    expect(evalConfigTypeLabel(config)).toBe("LLM as Judge")
  })
})

describe("evalConfigDetailsSummary", () => {
  describe("llm_judge", () => {
    it("returns the prompt template", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate the output quality.",
        required_var: [],
        g_eval: false,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "Evaluate the output quality.",
      )
    })

    it("includes system prompt when present", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate the output quality.",
        system_prompt: "You are an expert evaluator.",
        required_var: [],
        g_eval: false,
      })
      const summary = evalConfigDetailsSummary(config)
      expect(summary).toContain("Evaluate the output quality.")
      expect(summary).toContain("You are an expert evaluator.")
    })

    it("handles missing properties gracefully", () => {
      const config = makeV2Config("llm_judge", {})
      // Override properties to be null
      config.properties = null
      expect(evalConfigDetailsSummary(config)).toBe("No details available.")
    })
  })

  describe("code_eval", () => {
    it("returns the code", () => {
      const config = makeV2Config("code_eval", {
        code: "def score(output):\n  return 1.0",
        timeout_seconds: 30,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "def score(output):\n  return 1.0",
      )
    })

    it("handles missing code gracefully", () => {
      const config = makeV2Config("code_eval", {
        timeout_seconds: 30,
      })
      expect(evalConfigDetailsSummary(config)).toBe("No code provided.")
    })
  })

  describe("exact_match", () => {
    it("summarizes with expected_value", () => {
      const config = makeV2Config("exact_match", {
        value_expression: "user.status",
        expected_value: "active",
        case_sensitive: true,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        'Compare user.status to expected value "active"',
      )
    })

    it("summarizes with reference_key", () => {
      const config = makeV2Config("exact_match", {
        value_expression: "user.status",
        reference_key: "expected_user_status",
        case_sensitive: true,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "Compare user.status to reference_data.expected_user_status",
      )
    })

    it("includes case-insensitive note", () => {
      const config = makeV2Config("exact_match", {
        value_expression: "result",
        expected_value: "yes",
        case_sensitive: false,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        'Compare result to expected value "yes" (case-insensitive)',
      )
    })

    it("uses 'output' when value_expression is null", () => {
      const config = makeV2Config("exact_match", {
        expected_value: "hello",
        case_sensitive: true,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        'Compare output to expected value "hello"',
      )
    })
  })

  describe("pattern_match", () => {
    it("summarizes must_match pattern", () => {
      const config = makeV2Config("pattern_match", {
        value_expression: "response",
        pattern: "^\\d+$",
        mode: "must_match",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "response must match pattern /^\\d+$/",
      )
    })

    it("summarizes must_not_match pattern", () => {
      const config = makeV2Config("pattern_match", {
        pattern: "error",
        mode: "must_not_match",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "output must not match pattern /error/",
      )
    })
  })

  describe("contains", () => {
    it("summarizes must_contain with substring", () => {
      const config = makeV2Config("contains", {
        value_expression: "response",
        substring: "success",
        case_sensitive: true,
        mode: "must_contain",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        'response must contain "success"',
      )
    })

    it("summarizes must_not_contain with reference_key", () => {
      const config = makeV2Config("contains", {
        reference_key: "forbidden_word",
        case_sensitive: false,
        mode: "must_not_contain",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "output must not contain reference_data.forbidden_word (case-insensitive)",
      )
    })
  })

  describe("set_check", () => {
    it("summarizes with expected_set", () => {
      const config = makeV2Config("set_check", {
        value_expression: "tags",
        expected_set: ["a", "b", "c"],
        mode: "equal",
      })
      expect(evalConfigDetailsSummary(config)).toBe("tags equals {a, b, c}")
    })

    it("summarizes with reference_key", () => {
      const config = makeV2Config("set_check", {
        reference_key: "expected_tags",
        mode: "subset",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "output is a subset of reference_data.expected_tags",
      )
    })

    it("summarizes superset mode", () => {
      const config = makeV2Config("set_check", {
        value_expression: "items",
        expected_set: ["x"],
        mode: "superset",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "items is a superset of {x}",
      )
    })
  })

  describe("tool_call_check", () => {
    it("summarizes expected tools with match_mode", () => {
      const config = makeV2Config("tool_call_check", {
        expected_tools: [
          { tool_name: "search", expected_args: null },
          { tool_name: "fetch", expected_args: null },
        ],
        match_mode: "all",
        on_unexpected_tools: "ignore",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "Expect all of: search, fetch",
      )
    })

    it("includes fail on unexpected tools note", () => {
      const config = makeV2Config("tool_call_check", {
        expected_tools: [{ tool_name: "submit", expected_args: null }],
        match_mode: "ordered",
        on_unexpected_tools: "fail",
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "Expect in order: submit (fail on unexpected tools)",
      )
    })

    it("summarizes never mode", () => {
      const config = makeV2Config("tool_call_check", {
        expected_tools: [{ tool_name: "delete", expected_args: null }],
        match_mode: "never",
        on_unexpected_tools: "ignore",
      })
      expect(evalConfigDetailsSummary(config)).toBe("Expect never call: delete")
    })
  })

  describe("step_count_check", () => {
    it("summarizes with min and max", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "tool_calls",
        min_count: 1,
        max_count: 5,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "Count tool calls: min 1, max 5",
      )
    })

    it("summarizes with only min", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "model_responses",
        min_count: 3,
      })
      expect(evalConfigDetailsSummary(config)).toBe(
        "Count model responses: min 3",
      )
    })

    it("summarizes with only max", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "turns",
        max_count: 10,
      })
      expect(evalConfigDetailsSummary(config)).toBe("Count turns: max 10")
    })

    it("summarizes with no bounds", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "turns",
      })
      expect(evalConfigDetailsSummary(config)).toBe("Count turns")
    })
  })

  describe("legacy configs", () => {
    it("returns task_description for legacy config", () => {
      const config = makeLegacyConfig("g_eval", {
        task_description: "Evaluate quality of the response.",
        eval_steps: ["Check grammar", "Check relevance"],
      })
      const summary = evalConfigDetailsSummary(config)
      expect(summary).toContain("Evaluate quality of the response.")
      expect(summary).toContain("Steps:\n1. Check grammar\n2. Check relevance")
    })

    it("handles legacy config with no properties", () => {
      const config = makeLegacyConfig("g_eval")
      expect(evalConfigDetailsSummary(config)).toBe("No details available.")
    })
  })

  describe("exhaustive switch guard", () => {
    // This test documents the compile-time exhaustiveness guarantee:
    // The v2ConfigSummary function uses a `switch` over V2EvalType with
    // `default: return assertNever(type)`. If a new V2EvalType value is
    // added to the union in registry.ts without adding a corresponding
    // case in eval_config_summary.ts, TypeScript will report a compile
    // error because the new value cannot be assigned to `never`.
    // This is verified by `npm run check` (svelte-check / tsc).
    it("covers all V2 eval types", () => {
      const allTypes: V2EvalType[] = [
        "llm_judge",
        "code_eval",
        "exact_match",
        "pattern_match",
        "contains",
        "set_check",
        "tool_call_check",
        "step_count_check",
      ]
      for (const type of allTypes) {
        const config = makeV2Config(type, getMinimalPropsForType(type))
        // Should not throw — every type has a handler
        expect(() => evalConfigDetailsSummary(config)).not.toThrow()
      }
    })
  })
})

// Provide minimal valid properties for each type so the summary functions
// don't hit null paths.
function getMinimalPropsForType(type: V2EvalType): Record<string, unknown> {
  switch (type) {
    case "llm_judge":
      return {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "test",
        required_var: [],
        g_eval: false,
      }
    case "code_eval":
      return { code: "return 1", timeout_seconds: 30 }
    case "exact_match":
      return { expected_value: "x", case_sensitive: true }
    case "pattern_match":
      return { pattern: "x", mode: "must_match" }
    case "contains":
      return { substring: "x", case_sensitive: true, mode: "must_contain" }
    case "set_check":
      return { expected_set: ["a"], mode: "equal" }
    case "tool_call_check":
      return {
        expected_tools: [{ tool_name: "t", expected_args: null }],
        match_mode: "all",
        on_unexpected_tools: "ignore",
      }
    case "step_count_check":
      return { count_type: "tool_calls", min_count: 1 }
    default:
      throw new Error(`Unknown type: ${type}`)
  }
}
