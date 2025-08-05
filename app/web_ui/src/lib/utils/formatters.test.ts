import { describe, it, expect } from "vitest"
import { structuredOutputModeToString } from "./formatters"
import type { StructuredOutputMode } from "$lib/types"

describe("formatters", () => {
  describe("structuredOutputModeToString", () => {
    it("should convert 'default' to 'Default (Legacy)'", () => {
      expect(structuredOutputModeToString("default")).toBe("Default (Legacy)")
    })

    it("should convert 'json_schema' to 'JSON Schema'", () => {
      expect(structuredOutputModeToString("json_schema")).toBe("JSON Schema")
    })

    it("should convert 'function_calling_weak' to 'Weak Function Calling'", () => {
      expect(structuredOutputModeToString("function_calling_weak")).toBe(
        "Weak Function Calling",
      )
    })

    it("should convert 'function_calling' to 'Function Calling'", () => {
      expect(structuredOutputModeToString("function_calling")).toBe(
        "Function Calling",
      )
    })

    it("should convert 'json_mode' to 'JSON Mode'", () => {
      expect(structuredOutputModeToString("json_mode")).toBe("JSON Mode")
    })

    it("should convert 'json_instructions' to 'JSON Instructions'", () => {
      expect(structuredOutputModeToString("json_instructions")).toBe(
        "JSON Instructions",
      )
    })

    it("should convert 'json_instruction_and_object' to 'JSON Instructions + Mode'", () => {
      expect(structuredOutputModeToString("json_instruction_and_object")).toBe(
        "JSON Instructions + Mode",
      )
    })

    it("should convert 'json_custom_instructions' to 'None'", () => {
      expect(structuredOutputModeToString("json_custom_instructions")).toBe(
        "None",
      )
    })

    it("should convert 'unknown' to 'Unknown'", () => {
      expect(structuredOutputModeToString("unknown")).toBe("Unknown")
    })

    it("should handle all valid StructuredOutputMode values", () => {
      const testCases: Array<[StructuredOutputMode, string]> = [
        ["default", "Default (Legacy)"],
        ["json_schema", "JSON Schema"],
        ["function_calling_weak", "Weak Function Calling"],
        ["function_calling", "Function Calling"],
        ["json_mode", "JSON Mode"],
        ["json_instructions", "JSON Instructions"],
        ["json_instruction_and_object", "JSON Instructions + Mode"],
        ["json_custom_instructions", "None"],
        ["unknown", "Unknown"],
      ]

      testCases.forEach(([mode, expected]) => {
        expect(structuredOutputModeToString(mode)).toBe(expected)
      })
    })
  })
})
