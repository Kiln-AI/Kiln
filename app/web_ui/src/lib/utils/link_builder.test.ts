import { describe, it, expect } from "vitest"
import { prompt_link } from "./link_builder"

describe("prompt_link", () => {
  const mockProjectId = "test-project"
  const mockTaskId = "test-task"

  describe("parameter validation", () => {
    it("returns undefined when project_id is missing", () => {
      const result = prompt_link("", mockTaskId, "123456")
      expect(result).toBeUndefined()
    })

    it("returns undefined when task_id is missing", () => {
      const result = prompt_link(mockProjectId, "", "123456")
      expect(result).toBeUndefined()
    })

    it("returns undefined when prompt_id is missing", () => {
      const result = prompt_link(mockProjectId, mockTaskId, "")
      expect(result).toBeUndefined()
    })

    it("returns undefined when all parameters are missing", () => {
      const result = prompt_link("", "", "")
      expect(result).toBeUndefined()
    })
  })

  describe("fine-tuned prompts", () => {
    it("handles fine-tuned prompt with simple ID", () => {
      const promptId = "fine_tune_prompt::123456"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/fine_tune/${mockProjectId}/${mockTaskId}/fine_tune/123456`,
      )
    })

    it("handles fine-tuned prompt with complex ID containing double colons", () => {
      const promptId = "fine_tune_prompt::789123::456789::987654"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      // Should extract the last part after the final "::"
      expect(result).toBe(
        `/fine_tune/${mockProjectId}/${mockTaskId}/fine_tune/987654`,
      )
    })

    it("handles fine-tuned prompt with no additional parts", () => {
      const promptId = "fine_tune_prompt::"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/fine_tune/${mockProjectId}/${mockTaskId}/fine_tune/`,
      )
    })

    it("handles fine-tuned prompt with multiple numeric IDs", () => {
      const promptId =
        "fine_tune_prompt::306673458440::629828465317::310597603461"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      // Should extract the last numeric ID
      expect(result).toBe(
        `/fine_tune/${mockProjectId}/${mockTaskId}/fine_tune/310597603461`,
      )
    })

    it("URL encodes fine-tuned prompt IDs with special characters", () => {
      const promptId = "fine_tune_prompt::123456789"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/fine_tune/${mockProjectId}/${mockTaskId}/fine_tune/123456789`,
      )
    })
  })

  describe("generator prompts (non-ID style)", () => {
    it("links to generator_details for prompts without double colons", () => {
      const promptId = "987654321"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/prompts/${mockProjectId}/${mockTaskId}/generator_details/987654321`,
      )
    })

    it("URL encodes generator prompt IDs with special characters", () => {
      const promptId = "456789123"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/prompts/${mockProjectId}/${mockTaskId}/generator_details/456789123`,
      )
    })
  })

  describe("saved prompts (ID style)", () => {
    it("links to saved prompts for prompts with double colons", () => {
      const promptId = "111222::333444::555666"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/prompts/${mockProjectId}/${mockTaskId}/saved/111222%3A%3A333444%3A%3A555666`,
      )
    })

    it("handles saved prompts with single double colon", () => {
      const promptId = "777888::999000"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/prompts/${mockProjectId}/${mockTaskId}/saved/777888%3A%3A999000`,
      )
    })

    it("URL encodes saved prompt IDs with special characters", () => {
      const promptId = "123456::789012"
      const result = prompt_link(mockProjectId, mockTaskId, promptId)

      expect(result).toBe(
        `/prompts/${mockProjectId}/${mockTaskId}/saved/123456%3A%3A789012`,
      )
    })
  })

  describe("edge cases", () => {
    it("handles project and task IDs that need URL encoding", () => {
      const projectWithSpaces = "project with spaces"
      const taskWithSymbols = "task&symbols"
      const promptId = "555777999"

      const result = prompt_link(projectWithSpaces, taskWithSymbols, promptId)

      expect(result).toBe(
        `/prompts/project with spaces/task&symbols/generator_details/555777999`,
      )
    })

    it("distinguishes between fine-tune and regular prompts with similar prefixes", () => {
      const regularPrompt = "111333555"
      const result = prompt_link(mockProjectId, mockTaskId, regularPrompt)

      expect(result).toBe(
        `/prompts/${mockProjectId}/${mockTaskId}/generator_details/111333555`,
      )
    })
  })
})
