import { describe, it, expect } from "vitest"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
  getV2TypeFromEvalConfig,
  buildV2EvalTypeRegistry,
  extractV2Props,
  type V2EvalType,
  type V2EvalTypeMetadata,
} from "./registry"
import type { EvalConfig } from "$lib/types"

const EXPECTED_TYPES: V2EvalType[] = [
  "exact_match",
  "pattern_match",
  "contains",
  "set_check",
  "tool_call_check",
  "step_count_check",
  "llm_judge",
  "code_eval",
]

describe("ALL_V2_EVAL_TYPES", () => {
  it("contains exactly the expected entries", () => {
    expect(ALL_V2_EVAL_TYPES).toHaveLength(EXPECTED_TYPES.length)
  })

  it("contains all expected type values", () => {
    for (const t of EXPECTED_TYPES) {
      expect(ALL_V2_EVAL_TYPES).toContain(t)
    }
  })

  it("has no duplicates", () => {
    const unique = new Set(ALL_V2_EVAL_TYPES)
    expect(unique.size).toBe(ALL_V2_EVAL_TYPES.length)
  })
})

describe("getV2EvalTypeMetadata", () => {
  it("returns metadata with all required fields for every type", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      const meta = getV2EvalTypeMetadata(t)
      expect(meta.label).toBeTruthy()
      expect(meta.description).toBeTruthy()
      expect(meta.icon).toBeTruthy()
      expect(typeof meta.requiresTrust).toBe("boolean")
      expect(meta.createFormComponent).toBeTruthy()
      expect(meta.resultRendererComponent).toBeTruthy()
    }
  })

  it("returns correct label for each type", () => {
    const expectedLabels: Record<V2EvalType, string> = {
      exact_match: "Exact Match",
      pattern_match: "Pattern Match",
      contains: "Contains",
      set_check: "Set Check",
      tool_call_check: "Tool Call Check",
      step_count_check: "Step Count Check",
      llm_judge: "LLM as Judge (recommended)",
      code_eval: "Code Eval",
    }
    for (const [type, label] of Object.entries(expectedLabels)) {
      expect(getV2EvalTypeMetadata(type as V2EvalType).label).toBe(label)
    }
  })

  it("only code_eval requires trust", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      const meta = getV2EvalTypeMetadata(t)
      if (t === "code_eval") {
        expect(meta.requiresTrust).toBe(true)
      } else {
        expect(meta.requiresTrust).toBe(false)
      }
    }
  })

  it("icons start with 'bi bi-'", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      expect(getV2EvalTypeMetadata(t).icon).toMatch(/^bi bi-/)
    }
  })

  it("throws for an invalid type via assertNever", () => {
    expect(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      getV2EvalTypeMetadata("invalid_type" as any),
    ).toThrow("Unexpected value")
  })

  it("returns distinct form components for different types", () => {
    const components = new Set<V2EvalTypeMetadata["createFormComponent"]>()
    for (const t of ALL_V2_EVAL_TYPES) {
      components.add(getV2EvalTypeMetadata(t).createFormComponent)
    }
    expect(components.size).toBe(ALL_V2_EVAL_TYPES.length)
  })
})

describe("getV2TypeFromEvalConfig", () => {
  it("returns the V2 type for a valid v2 config", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      const result = getV2TypeFromEvalConfig({
        config_type: "v2",
        properties: { type: t },
      })
      expect(result).toBe(t)
    }
  })

  it("returns null for a legacy g_eval config", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "g_eval",
        properties: { type: "exact_match" },
      }),
    ).toBeNull()
  })

  it("returns null for a legacy llm_as_judge config", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "llm_as_judge",
        properties: null,
      }),
    ).toBeNull()
  })

  it("returns null when properties is null", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "v2",
        properties: null,
      }),
    ).toBeNull()
  })

  it("returns null when properties is undefined", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "v2",
      }),
    ).toBeNull()
  })

  it("returns null when properties has no type field", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "v2",
        properties: {},
      }),
    ).toBeNull()
  })

  it("returns null for an unrecognized V2 type string", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "v2",
        properties: { type: "not_a_real_type" },
      }),
    ).toBeNull()
  })

  it("returns null when type is a non-string value", () => {
    expect(
      getV2TypeFromEvalConfig({
        config_type: "v2",
        properties: { type: 42 as unknown as string },
      }),
    ).toBeNull()
  })
})

describe("buildV2EvalTypeRegistry", () => {
  it("returns a Map with an entry for every type", () => {
    const registry = buildV2EvalTypeRegistry()
    expect(registry.size).toBe(ALL_V2_EVAL_TYPES.length)
    for (const t of ALL_V2_EVAL_TYPES) {
      expect(registry.has(t)).toBe(true)
    }
  })

  it("registry values match getV2EvalTypeMetadata", () => {
    const registry = buildV2EvalTypeRegistry()
    for (const t of ALL_V2_EVAL_TYPES) {
      const fromRegistry = registry.get(t)!
      const fromFn = getV2EvalTypeMetadata(t)
      expect(fromRegistry.label).toBe(fromFn.label)
      expect(fromRegistry.description).toBe(fromFn.description)
      expect(fromRegistry.icon).toBe(fromFn.icon)
      expect(fromRegistry.requiresTrust).toBe(fromFn.requiresTrust)
      expect(fromRegistry.createFormComponent).toBe(fromFn.createFormComponent)
      expect(fromRegistry.resultRendererComponent).toBe(
        fromFn.resultRendererComponent,
      )
    }
  })
})

describe("extractV2Props", () => {
  function makeEvalConfig(
    properties: Record<string, unknown> | null,
  ): EvalConfig {
    return {
      v: 1,
      name: "test",
      config_type: "v2",
      model_type: "eval_config",
      properties,
    } as EvalConfig
  }

  it("returns typed properties when type matches", () => {
    const config = makeEvalConfig({
      type: "exact_match",
      case_sensitive: true,
      expected_value: "hello",
      reference_key: null,
      value_expression: null,
    })
    const result = extractV2Props(config, "exact_match")
    expect(result).not.toBeNull()
    expect(result!.type).toBe("exact_match")
    expect(result!.case_sensitive).toBe(true)
    expect(result!.expected_value).toBe("hello")
  })

  it("returns null when type discriminator does not match", () => {
    const config = makeEvalConfig({
      type: "contains",
      case_sensitive: false,
      mode: "must_contain",
    })
    const result = extractV2Props(config, "exact_match")
    expect(result).toBeNull()
  })

  it("returns null when eval_config is null", () => {
    expect(extractV2Props(null, "exact_match")).toBeNull()
  })

  it("returns null when properties is null", () => {
    const config = makeEvalConfig(null)
    expect(extractV2Props(config, "exact_match")).toBeNull()
  })

  it("returns null when properties has no type field", () => {
    const config = makeEvalConfig({ case_sensitive: true })
    expect(extractV2Props(config, "exact_match")).toBeNull()
  })

  it("works for each V2 type", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      const config = makeEvalConfig({ type: t })
      const result = extractV2Props(config, t)
      expect(result).not.toBeNull()
      expect(result!.type).toBe(t)
    }
  })
})
