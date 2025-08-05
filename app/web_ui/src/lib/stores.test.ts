import { get } from "svelte/store"
import {
  projects,
  current_project,
  ui_state,
  default_ui_state,
  available_models,
  provider_name_from_id,
  structuredOutputModeToString,
} from "./stores"
import { describe, it, expect, beforeEach } from "vitest"
import type { StructuredOutputMode } from "./types"

const testProject = {
  v: 1,
  id: "test-project-id",
  name: "Test Project",
  path: "/test/path",
  description: "Test Description",
  created_at: new Date().toISOString(),
  created_by: "Test User",
}

describe("stores", () => {
  beforeEach(() => {
    // Reset the projects store before each test
    projects.set(null)
    current_project.set(null)
    ui_state.set(default_ui_state)
    // Reset the available_models store before each test
    available_models.set([])
  })

  describe("projects store", () => {
    it("should initialize with null", () => {
      expect(get(projects)).toBeNull()
    })

    it("should update when set", () => {
      const testProjects = {
        projects: [testProject],
        current_project_id: "test-project-id",
        error: null,
      }
      projects.set(testProjects)
      expect(get(projects)).toEqual(testProjects)
    })
  })

  describe("current_project", () => {
    it("should return null when projects store is null", () => {
      expect(get(current_project)).toBeNull()
    })

    it("should return null when current_project_id is null", () => {
      projects.set({
        projects: [testProject],
        error: null,
      })
      ui_state.set({
        current_project_id: null,
      })
      expect(get(current_project)).toBeNull()
    })

    it("should return null when no project matches current_project_id", () => {
      projects.set({
        projects: [testProject],
        error: null,
      })
      ui_state.set({
        current_project_id: "non-existent-project-id",
      })
      expect(get(current_project)).toBeNull()
    })

    it("should return the correct project when it exists", () => {
      projects.set({
        projects: [testProject],
        error: null,
      })
      ui_state.set({
        current_project_id: "test-project-id",
      })
      expect(get(current_project)).toEqual(testProject)
    })
  })

  describe("provider_name_from_id", () => {
    it("should return 'Unknown' when provider_id is empty", () => {
      expect(provider_name_from_id("")).toBe("Unknown")
    })

    it("should return provider_name when provider exists", () => {
      available_models.set([
        {
          provider_id: "test-provider",
          provider_name: "Test Provider",
          models: [],
        },
      ])
      expect(provider_name_from_id("test-provider")).toBe("Test Provider")
    })

    it("should return provider_id when provider doesn't exist", () => {
      available_models.set([])
      expect(provider_name_from_id("non-existent-provider")).toBe(
        "non-existent-provider",
      )
    })
  })

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
