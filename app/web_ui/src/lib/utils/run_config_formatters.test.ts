import { describe, it, expect, vi } from "vitest"
import type { TaskRunConfig, InputTransform, PromptResponse } from "$lib/types"
import {
  getRunConfigModelDisplayName,
  getRunConfigUiProperties,
  getRunConfigPromptDisplayName,
  getRunConfigPromptInfoText,
  getInputTransformDisplay,
  getRunConfigInputTransform,
  getRunConfigInputTransformSummaryLabel,
  buildJinjaInputTransform,
  inputTransformsEqual,
  getThinkingLevelDisplayName,
} from "./run_config_formatters"

const JINJA_TRANSFORM: InputTransform = {
  type: "jinja",
  template: "Hello {{ input }}",
}

function makeKilnAgentConfig(
  overrides: Partial<TaskRunConfig> & {
    input_transform?: InputTransform | null
    thinking_level?: string | null
  } = {},
): TaskRunConfig {
  const { input_transform, thinking_level, ...rest } = overrides
  return {
    v: 1,
    id: "rc-agent",
    created_at: "2026-02-01T00:00:00.000Z",
    created_by: "test",
    name: "Agent Config",
    description: null,
    run_config_properties: {
      type: "kiln_agent",
      model_name: "gpt-4",
      model_provider_name: "openai",
      prompt_id: "p1",
      temperature: 0.7,
      top_p: 1,
      structured_output_mode: "default",
      input_transform: input_transform ?? null,
      thinking_level: thinking_level ?? null,
    },
    prompt: null,
    model_type: "task_run_config",
    starred: false,
    ...rest,
  }
}

describe("run_config_formatters (MCP)", () => {
  const mcp_config: TaskRunConfig = {
    v: 1,
    id: "rc1",
    created_at: "2026-02-01T00:00:00.000Z",
    created_by: "test",
    name: "MCP Config",
    description: null,
    run_config_properties: {
      type: "mcp",
      tool_reference: {
        tool_id: "mcp::local::server::tool",
        tool_name: "Demo Tool",
        input_schema: { type: "object", properties: {} },
        output_schema: null,
      },
    },
    prompt: null,
    model_type: "task_run_config",
    starred: false,
  }

  it("getRunConfigModelDisplayName should return MCP tool name", () => {
    expect(getRunConfigModelDisplayName(mcp_config, null)).toBe(null)
  })

  it("getRunConfigUiProperties should return MCP-specific fields", () => {
    const props = getRunConfigUiProperties(
      "project1",
      "task1",
      mcp_config,
      null,
      null,
      null,
    )
    const propNames = props.map((p) => p.name)
    expect(propNames).toContain("Type")
    expect(propNames).toContain("MCP Tool")
    expect(propNames).toContain("Tool ID")
    expect(propNames).not.toContain("Model")
    expect(propNames).not.toContain("Prompt")
    expect(propNames).not.toContain("Input Transformer")
    const typeProp = props.find((p) => p.name === "Type")
    expect(typeProp?.value).toBe("MCP Tool (No Agent)")
  })

  it("getRunConfigInputTransform should return null for MCP", () => {
    expect(getRunConfigInputTransform(mcp_config)).toBeNull()
  })

  it("getRunConfigInputTransformSummaryLabel should return null for MCP", () => {
    expect(getRunConfigInputTransformSummaryLabel(mcp_config)).toBeNull()
  })
})

describe("getInputTransformDisplay", () => {
  it("returns correct labels for jinja transform", () => {
    const result = getInputTransformDisplay(JINJA_TRANSFORM)
    expect(result.valueLabel).toBe("Custom Template")
    expect(result.summaryLabel).toBe("Custom")
    expect(result.modalSubtitle).toBe("Type: Custom Jinja2 Template")
  })
})

describe("getRunConfigInputTransform", () => {
  it("returns null for kiln_agent without transform", () => {
    const config = makeKilnAgentConfig()
    expect(getRunConfigInputTransform(config)).toBeNull()
  })

  it("returns null for kiln_agent with undefined input_transform", () => {
    const config = makeKilnAgentConfig()
    // Simulate absent field by deleting it
    delete (config.run_config_properties as Record<string, unknown>)
      .input_transform
    expect(getRunConfigInputTransform(config)).toBeNull()
  })

  it("returns the transform for kiln_agent with jinja transform", () => {
    const config = makeKilnAgentConfig({ input_transform: JINJA_TRANSFORM })
    const result = getRunConfigInputTransform(config)
    expect(result).toEqual(JINJA_TRANSFORM)
    expect(result?.type).toBe("jinja")
  })
})

describe("getRunConfigInputTransformSummaryLabel", () => {
  it("returns null when absent", () => {
    const config = makeKilnAgentConfig()
    expect(getRunConfigInputTransformSummaryLabel(config)).toBeNull()
  })

  it('returns "Custom" for jinja transform', () => {
    const config = makeKilnAgentConfig({ input_transform: JINJA_TRANSFORM })
    expect(getRunConfigInputTransformSummaryLabel(config)).toBe("Custom")
  })
})

describe("getRunConfigUiProperties (kiln_agent input transformer row)", () => {
  it('shows "None" without action when no transform', () => {
    const config = makeKilnAgentConfig()
    const callback = vi.fn()
    const props = getRunConfigUiProperties(
      "p1",
      "t1",
      config,
      null,
      null,
      null,
      callback,
    )
    const row = props.find((p) => p.name === "Input Transformer")
    expect(row).toBeDefined()
    expect(row?.value).toBe("None")
    expect(row?.action).toBeUndefined()
  })

  it('shows "Custom Template" with action when jinja transform present', () => {
    const config = makeKilnAgentConfig({ input_transform: JINJA_TRANSFORM })
    const callback = vi.fn()
    const props = getRunConfigUiProperties(
      "p1",
      "t1",
      config,
      null,
      null,
      null,
      callback,
    )
    const row = props.find((p) => p.name === "Input Transformer")
    expect(row).toBeDefined()
    expect(row?.value).toBe("Custom Template")
    expect(row?.action).toBe(callback)
  })

  it("has no action when transform present but no callback provided", () => {
    const config = makeKilnAgentConfig({ input_transform: JINJA_TRANSFORM })
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const row = props.find((p) => p.name === "Input Transformer")
    expect(row).toBeDefined()
    expect(row?.value).toBe("Custom Template")
    expect(row?.action).toBeUndefined()
  })

  it("places Input Transformer row after Prompt", () => {
    const config = makeKilnAgentConfig()
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const names = props.map((p) => p.name)
    const promptIdx = names.indexOf("Prompt")
    const transformIdx = names.indexOf("Input Transformer")
    expect(promptIdx).toBeGreaterThanOrEqual(0)
    expect(transformIdx).toBe(promptIdx + 1)
  })
})

describe("getThinkingLevelDisplayName", () => {
  it("maps known thinking level values to friendly labels", () => {
    expect(getThinkingLevelDisplayName("none")).toBe("None")
    expect(getThinkingLevelDisplayName("minimal")).toBe("Minimal")
    expect(getThinkingLevelDisplayName("low")).toBe("Low")
    expect(getThinkingLevelDisplayName("medium")).toBe("Medium")
    expect(getThinkingLevelDisplayName("high")).toBe("High")
    expect(getThinkingLevelDisplayName("xhigh")).toBe("Extra High")
    expect(getThinkingLevelDisplayName("max")).toBe("Max")
  })

  it("capitalizes unknown values as a fallback", () => {
    expect(getThinkingLevelDisplayName("ultra")).toBe("Ultra")
  })
})

describe("getRunConfigUiProperties (kiln_agent thinking level row)", () => {
  it("shows the Thinking Level row when a value is set", () => {
    const config = makeKilnAgentConfig({ thinking_level: "high" })
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const row = props.find((p) => p.name === "Thinking Level")
    expect(row).toBeDefined()
    expect(row?.value).toBe("High")
  })

  it('shows "None" when thinking level is explicitly "none"', () => {
    const config = makeKilnAgentConfig({ thinking_level: "none" })
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const row = props.find((p) => p.name === "Thinking Level")
    expect(row).toBeDefined()
    expect(row?.value).toBe("None")
  })

  it("omits the Thinking Level row when thinking level is null", () => {
    const config = makeKilnAgentConfig({ thinking_level: null })
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const names = props.map((p) => p.name)
    expect(names).not.toContain("Thinking Level")
  })

  it("omits the Thinking Level row when thinking_level is undefined/absent", () => {
    const config = makeKilnAgentConfig()
    delete (config.run_config_properties as Record<string, unknown>)
      .thinking_level
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const names = props.map((p) => p.name)
    expect(names).not.toContain("Thinking Level")
  })

  it("places the Thinking Level row after Top P", () => {
    const config = makeKilnAgentConfig({ thinking_level: "medium" })
    const props = getRunConfigUiProperties("p1", "t1", config, null, null, null)
    const names = props.map((p) => p.name)
    const topPIdx = names.indexOf("Top P")
    const thinkingIdx = names.indexOf("Thinking Level")
    expect(topPIdx).toBeGreaterThanOrEqual(0)
    expect(thinkingIdx).toBe(topPIdx + 1)
  })
})

describe("buildJinjaInputTransform", () => {
  it("builds a jinja input transform from a template string", () => {
    const result = buildJinjaInputTransform("Hello {{ input }}")
    expect(result).toEqual({ type: "jinja", template: "Hello {{ input }}" })
  })

  it("preserves empty strings", () => {
    const result = buildJinjaInputTransform("")
    expect(result).toEqual({ type: "jinja", template: "" })
  })
})

describe("inputTransformsEqual", () => {
  it("returns true for null/null", () => {
    expect(inputTransformsEqual(null, null)).toBe(true)
  })

  it("returns true for undefined/undefined", () => {
    expect(inputTransformsEqual(undefined, undefined)).toBe(true)
  })

  it("returns true for null/undefined", () => {
    expect(inputTransformsEqual(null, undefined)).toBe(true)
  })

  it("returns false for null/set", () => {
    expect(inputTransformsEqual(null, JINJA_TRANSFORM)).toBe(false)
  })

  it("returns false for set/null", () => {
    expect(inputTransformsEqual(JINJA_TRANSFORM, null)).toBe(false)
  })

  it("returns false for undefined/set", () => {
    expect(inputTransformsEqual(undefined, JINJA_TRANSFORM)).toBe(false)
  })

  it("returns false for set/undefined", () => {
    expect(inputTransformsEqual(JINJA_TRANSFORM, undefined)).toBe(false)
  })

  it("returns true for same template", () => {
    const a = { type: "jinja" as const, template: "Hello {{ input }}" }
    const b = { type: "jinja" as const, template: "Hello {{ input }}" }
    expect(inputTransformsEqual(a, b)).toBe(true)
  })

  it("returns false for different templates", () => {
    const a = { type: "jinja" as const, template: "Hello {{ input }}" }
    const b = { type: "jinja" as const, template: "Goodbye {{ input }}" }
    expect(inputTransformsEqual(a, b)).toBe(false)
  })
})

describe("run_config_formatters (frozen prompt display)", () => {
  // The prompts list contains the OWNER run config's frozen prompt by id.
  const OWNER_PROMPT_ID = "task_run_config::p1::t1::owner"
  // The type is baked into the frozen prompt's name at creation time.
  const FROZEN_NAME = "Ethereal Owl - Basic (Zero Shot)"
  const prompts: PromptResponse = {
    generators: [],
    prompts: [
      {
        id: OWNER_PROMPT_ID,
        type: "Frozen",
        name: FROZEN_NAME,
        prompt: "frozen body",
        description: null,
        generator_id: "simple_prompt_builder",
        chain_of_thought_instructions: null,
        created_at: "2026-02-01T00:00:00.000Z",
        created_by: "test",
      },
    ],
  }

  it("shows the baked name when the run config owns its frozen prompt", () => {
    const owner = makeKilnAgentConfig({
      id: "owner",
      run_config_properties: {
        type: "kiln_agent",
        model_name: "gpt-4",
        model_provider_name: "openai",
        prompt_id: OWNER_PROMPT_ID,
        temperature: 0.7,
        top_p: 1,
        structured_output_mode: "default",
        input_transform: null,
        thinking_level: null,
      },
      prompt: {
        name: FROZEN_NAME,
        prompt: "frozen body",
        description: null,
        generator_id: "simple_prompt_builder",
        chain_of_thought_instructions: null,
      },
    })
    // No runtime type label is appended; the name carries it.
    expect(getRunConfigPromptDisplayName(owner, prompts)).toBe(FROZEN_NAME)
  })

  it("resolves the owner's name for a reused frozen prompt (no local copy)", () => {
    // A run config that reuses another's frozen prompt: prompt is null, but the
    // prompt_id points at the owner's frozen prompt in the prompts list.
    const reuser = makeKilnAgentConfig({
      id: "reuser",
      run_config_properties: {
        type: "kiln_agent",
        model_name: "gpt-4",
        model_provider_name: "openai",
        prompt_id: OWNER_PROMPT_ID,
        temperature: 0.7,
        top_p: 1,
        structured_output_mode: "default",
        input_transform: null,
        thinking_level: null,
      },
      prompt: null,
    })
    expect(getRunConfigPromptDisplayName(reuser, prompts)).toBe(FROZEN_NAME)
    // Info text resolves the name from the prompts list too
    expect(getRunConfigPromptInfoText(reuser, prompts)).toContain(
      `saved under the name "${FROZEN_NAME}"`,
    )
  })
})
