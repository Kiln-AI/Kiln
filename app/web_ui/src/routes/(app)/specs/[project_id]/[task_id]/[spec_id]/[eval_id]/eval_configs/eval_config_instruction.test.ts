// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import EvalConfigInstruction from "./eval_config_instruction.svelte"
import type { EvalConfig } from "$lib/types"
import { ALL_V2_EVAL_TYPES } from "$lib/utils/eval_types/registry"

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

function getMinimalPropsForType(type: string): Record<string, unknown> {
  switch (type) {
    case "llm_judge":
      return {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate the output.",
        reference_keys: [],
        g_eval: false,
      }
    case "code_eval":
      return { code: "def score(output):\n  return 1.0", timeout_seconds: 30 }
    case "exact_match":
      return { expected_value: "x", case_sensitive: true }
    case "pattern_match":
      return { pattern: "^\\d+$", mode: "must_match" }
    case "contains":
      return { substring: "hello", case_sensitive: true, mode: "must_contain" }
    case "set_check":
      return { expected_set: ["a", "b"], mode: "equal" }
    case "tool_call_check":
      return {
        expected_tools: [{ tool_name: "search", expected_args: null }],
        match_mode: "all",
        on_unexpected_tools: "ignore",
      }
    case "step_count_check":
      return { count_type: "tool_calls", min_count: 1, max_count: 5 }
    default:
      throw new Error(`Unknown type: ${type}`)
  }
}

describe("EvalConfigInstruction", () => {
  describe("judge metadata lines", () => {
    it("shows Judge Model and Provider for V2 llm_judge", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate the output.",
        reference_keys: [],
        g_eval: false,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      const modelLine = container.querySelector(
        '[data-testid="judge-model-line"]',
      )
      expect(modelLine).not.toBeNull()
      expect(modelLine!.textContent).toContain("Judge Model:")
      expect(modelLine!.textContent).toContain("gpt-4")

      const providerLine = container.querySelector(
        '[data-testid="judge-provider-line"]',
      )
      expect(providerLine).not.toBeNull()
      expect(providerLine!.textContent).toContain("Provider:")
      expect(providerLine!.textContent).toContain("OpenAI")
    })

    it("shows Method: G-Eval for V2 llm_judge with g_eval=true", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate.",
        reference_keys: [],
        g_eval: true,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      const methodLine = container.querySelector(
        '[data-testid="judge-method-line"]',
      )
      expect(methodLine).not.toBeNull()
      expect(methodLine!.textContent).toContain("Method:")
      expect(methodLine!.textContent).toContain("G-Eval")
    })

    it("does not show Method line for vanilla V2 llm_judge", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate.",
        reference_keys: [],
        g_eval: false,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(
        container.querySelector('[data-testid="judge-method-line"]'),
      ).toBeNull()
    })

    it("shows Judge Model and Provider for legacy g_eval config", () => {
      const config = makeLegacyConfig("g_eval", {
        task_description: "test",
      })
      config.model_name = "gpt-4o"
      config.model_provider = "openai"
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      const modelLine = container.querySelector(
        '[data-testid="judge-model-line"]',
      )
      expect(modelLine).not.toBeNull()
      expect(modelLine!.textContent).toContain("Judge Model:")
      expect(modelLine!.textContent).toContain("gpt-4o")

      const providerLine = container.querySelector(
        '[data-testid="judge-provider-line"]',
      )
      expect(providerLine).not.toBeNull()
      expect(providerLine!.textContent).toContain("Provider:")
      expect(providerLine!.textContent).toContain("OpenAI")
    })

    it("shows Method: G-Eval for legacy g_eval config", () => {
      const config = makeLegacyConfig("g_eval", {
        task_description: "test",
      })
      config.model_name = "gpt-4o"
      config.model_provider = "openai"
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      const methodLine = container.querySelector(
        '[data-testid="judge-method-line"]',
      )
      expect(methodLine).not.toBeNull()
      expect(methodLine!.textContent).toContain("G-Eval")
    })

    it("shows Judge Model and Provider but not Method for legacy llm_as_judge", () => {
      const config = makeLegacyConfig("llm_as_judge", {
        task_description: "test",
      })
      config.model_name = "gpt-4"
      config.model_provider = "openai"
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      const modelLine = container.querySelector(
        '[data-testid="judge-model-line"]',
      )
      expect(modelLine).not.toBeNull()
      expect(modelLine!.textContent).toContain("Judge Model:")
      expect(modelLine!.textContent).toContain("gpt-4")

      const providerLine = container.querySelector(
        '[data-testid="judge-provider-line"]',
      )
      expect(providerLine).not.toBeNull()
      expect(providerLine!.textContent).toContain("Provider:")
      expect(providerLine!.textContent).toContain("OpenAI")

      expect(
        container.querySelector('[data-testid="judge-method-line"]'),
      ).toBeNull()
    })

    it("does not render a Type: line (type is shown in the Judge column)", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate.",
        reference_keys: [],
        g_eval: false,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(
        container.querySelector('[data-testid="eval-config-type-label"]'),
      ).toBeNull()
    })

    it("does not show judge metadata for deterministic V2 evals", () => {
      const config = makeV2Config(
        "exact_match",
        getMinimalPropsForType("exact_match"),
      )
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(
        container.querySelector('[data-testid="judge-model-line"]'),
      ).toBeNull()
      expect(
        container.querySelector('[data-testid="judge-provider-line"]'),
      ).toBeNull()
      expect(
        container.querySelector('[data-testid="judge-method-line"]'),
      ).toBeNull()
    })
  })

  describe("llm_judge", () => {
    it("renders prompt template under Judge Prompt heading via Output component", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate the quality.",
        reference_keys: [],
        g_eval: false,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("Judge Prompt")
      expect(container.textContent).toContain("Evaluate the quality.")

      const styledBlock = container.querySelector(".bg-base-200 pre")
      expect(styledBlock).not.toBeNull()
      expect(styledBlock!.textContent).toContain("Evaluate the quality.")
    })

    it("renders system prompt when present", () => {
      const config = makeV2Config("llm_judge", {
        model_name: "gpt-4",
        model_provider: "openai",
        prompt_template: "Evaluate the quality.",
        system_prompt: "You are an expert.",
        reference_keys: [],
        g_eval: false,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("System prompt:")
      expect(container.textContent).toContain("You are an expert.")
    })

    it("shows fallback when no properties", () => {
      const config = makeV2Config("llm_judge", {})
      config.properties = null
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("No details available.")
    })
  })

  describe("code_eval", () => {
    it("renders code in a pre element with monospace", () => {
      const config = makeV2Config("code_eval", {
        code: "def score(output):\n  return 1.0",
        timeout_seconds: 30,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      const pre = container.querySelector(
        '[data-testid="code-eval-pre"]',
      ) as HTMLPreElement
      expect(pre).not.toBeNull()
      expect(pre.tagName).toBe("PRE")
      expect(pre.classList.contains("font-mono")).toBe(true)
      expect(pre.textContent).toContain("def score(output):")
      expect(pre.textContent).toContain("return 1.0")
    })

    it("shows fallback when no code", () => {
      const config = makeV2Config("code_eval", { timeout_seconds: 30 })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("No code provided.")
    })
  })

  describe("exact_match", () => {
    it("renders with expected_value", () => {
      const config = makeV2Config("exact_match", {
        value_expression: "user.status",
        expected_value: "active",
        case_sensitive: true,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("Compare")
      expect(container.textContent).toContain("user.status")
      expect(container.textContent).toContain('"active"')
    })

    it("renders with reference_key", () => {
      const config = makeV2Config("exact_match", {
        value_expression: "user.status",
        reference_key: "expected_user_status",
        case_sensitive: true,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain(
        "reference_data.expected_user_status",
      )
    })

    it("shows case-insensitive note", () => {
      const config = makeV2Config("exact_match", {
        expected_value: "yes",
        case_sensitive: false,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("(case-insensitive)")
    })

    it("uses 'output' when value_expression is null", () => {
      const config = makeV2Config("exact_match", {
        expected_value: "hello",
        case_sensitive: true,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("Compare")
      expect(container.textContent).toContain("output")
    })
  })

  describe("pattern_match", () => {
    it("renders must_match pattern", () => {
      const config = makeV2Config("pattern_match", {
        value_expression: "response",
        pattern: "^\\d+$",
        mode: "must_match",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("response")
      expect(container.textContent).toContain("must match")
      expect(container.textContent).toContain("/^\\d+$/")
    })

    it("renders must_not_match", () => {
      const config = makeV2Config("pattern_match", {
        pattern: "error",
        mode: "must_not_match",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("must not match")
      expect(container.textContent).toContain("/error/")
    })
  })

  describe("contains", () => {
    it("renders must_contain with substring", () => {
      const config = makeV2Config("contains", {
        value_expression: "response",
        substring: "success",
        case_sensitive: true,
        mode: "must_contain",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("must contain")
      expect(container.textContent).toContain('"success"')
    })

    it("renders must_not_contain with reference_key", () => {
      const config = makeV2Config("contains", {
        reference_key: "forbidden_word",
        case_sensitive: false,
        mode: "must_not_contain",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("must not contain")
      expect(container.textContent).toContain("reference_data.forbidden_word")
      expect(container.textContent).toContain("(case-insensitive)")
    })
  })

  describe("set_check", () => {
    it("renders with expected_set", () => {
      const config = makeV2Config("set_check", {
        value_expression: "tags",
        expected_set: ["a", "b", "c"],
        mode: "equal",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("tags")
      expect(container.textContent).toContain("equals")
      expect(container.textContent).toContain("{a, b, c}")
    })

    it("renders with reference_key", () => {
      const config = makeV2Config("set_check", {
        reference_key: "expected_tags",
        mode: "subset",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("is a subset of")
      expect(container.textContent).toContain("reference_data.expected_tags")
    })

    it("renders superset mode", () => {
      const config = makeV2Config("set_check", {
        value_expression: "items",
        expected_set: ["x"],
        mode: "superset",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("is a superset of")
    })
  })

  describe("tool_call_check", () => {
    it("renders expected tools with match_mode", () => {
      const config = makeV2Config("tool_call_check", {
        expected_tools: [
          { tool_name: "search", expected_args: null },
          { tool_name: "fetch", expected_args: null },
        ],
        match_mode: "all",
        on_unexpected_tools: "ignore",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("all of")
      expect(container.textContent).toContain("search, fetch")
    })

    it("shows fail on unexpected tools note", () => {
      const config = makeV2Config("tool_call_check", {
        expected_tools: [{ tool_name: "submit", expected_args: null }],
        match_mode: "ordered",
        on_unexpected_tools: "fail",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("in order")
      expect(container.textContent).toContain("(fail on unexpected tools)")
    })

    it("renders never mode", () => {
      const config = makeV2Config("tool_call_check", {
        expected_tools: [{ tool_name: "delete", expected_args: null }],
        match_mode: "never",
        on_unexpected_tools: "ignore",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("never call")
      expect(container.textContent).toContain("delete")
    })
  })

  describe("step_count_check", () => {
    it("renders with min and max", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "tool_calls",
        min_count: 1,
        max_count: 5,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("Count")
      expect(container.textContent).toContain("tool calls")
      expect(container.textContent).toContain("min")
      expect(container.textContent).toContain("1")
      expect(container.textContent).toContain("max")
      expect(container.textContent).toContain("5")
    })

    it("renders with only min", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "model_responses",
        min_count: 3,
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("model responses")
      expect(container.textContent).toContain("min")
      expect(container.textContent).toContain("3")
    })

    it("renders with no bounds", () => {
      const config = makeV2Config("step_count_check", {
        count_type: "turns",
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("Count")
      expect(container.textContent).toContain("turns")
    })
  })

  describe("legacy configs", () => {
    it("renders task_description and eval steps for g_eval", () => {
      const config = makeLegacyConfig("g_eval", {
        task_description: "Evaluate quality of the response.",
        eval_steps: ["Check grammar", "Check relevance"],
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain(
        "Evaluate quality of the response.",
      )
      expect(container.textContent).toContain("Check grammar")
      expect(container.textContent).toContain("Check relevance")
    })

    it("renders steps in an ordered list", () => {
      const config = makeLegacyConfig("g_eval", {
        eval_steps: ["Step 1", "Step 2"],
      })
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("Step 1")
      expect(container.textContent).toContain("Step 2")
    })

    it("shows fallback when no properties", () => {
      const config = makeLegacyConfig("g_eval")
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: config },
      })
      expect(container.textContent).toContain("No details available.")
    })
  })

  describe("exhaustive guard", () => {
    it("renders all V2 eval types without error", () => {
      for (const type of ALL_V2_EVAL_TYPES) {
        const config = makeV2Config(type, getMinimalPropsForType(type))
        const { container } = render(EvalConfigInstruction, {
          props: { eval_config: config },
        })
        expect(
          container.querySelector('[data-testid="eval-config-instruction"]'),
        ).not.toBeNull()
      }
    })
  })

  describe("null eval_config", () => {
    it("renders nothing when eval_config is null", () => {
      const { container } = render(EvalConfigInstruction, {
        props: { eval_config: null },
      })
      expect(
        container.querySelector('[data-testid="eval-config-instruction"]'),
      ).toBeNull()
    })
  })
})
