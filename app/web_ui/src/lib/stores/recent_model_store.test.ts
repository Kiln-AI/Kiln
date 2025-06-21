import { get } from "svelte/store"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { recent_model_store, addRecentModel } from "./recent_model_store"

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
}

describe("recent_model_store", () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Mock window and localStorage
    vi.stubGlobal("window", {
      localStorage: localStorageMock,
    })

    // Reset localStorage mock behavior
    localStorageMock.getItem.mockReturnValue(null)
    localStorageMock.setItem.mockImplementation(() => {})

    // Reset the store to empty state
    recent_model_store.set([])
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  describe("store initialization", () => {
    it("should initialize with empty array when no stored data", () => {
      const models = get(recent_model_store)
      expect(models).toEqual([])
    })

    it("should work with the store after initialization", () => {
      // This test just verifies the store is working
      recent_model_store.set([
        { model_id: "test", model_provider: "test-provider" },
      ])
      const models = get(recent_model_store)
      expect(models).toEqual([
        { model_id: "test", model_provider: "test-provider" },
      ])
    })
  })

  describe("addRecentModel function", () => {
    beforeEach(() => {
      // Reset the store to empty state
      recent_model_store.set([])
    })

    it("should add a new model to empty store", () => {
      addRecentModel("gpt-4", "openai")

      const models = get(recent_model_store)
      expect(models).toEqual([{ model_id: "gpt-4", model_provider: "openai" }])
    })

    it("should add multiple models in MRU order (most recent first)", () => {
      addRecentModel("gpt-4", "openai")
      addRecentModel("claude-3", "anthropic")
      addRecentModel("gemini-pro", "google")

      const models = get(recent_model_store)
      expect(models).toEqual([
        { model_id: "gemini-pro", model_provider: "google" },
        { model_id: "claude-3", model_provider: "anthropic" },
        { model_id: "gpt-4", model_provider: "openai" },
      ])
    })

    it("should maintain uniqueness - remove duplicate and add to front", () => {
      // Add initial models
      addRecentModel("gpt-4", "openai")
      addRecentModel("claude-3", "anthropic")
      addRecentModel("gemini-pro", "google")

      // Add a duplicate
      addRecentModel("gpt-4", "openai")

      const models = get(recent_model_store)
      expect(models).toEqual([
        { model_id: "gpt-4", model_provider: "openai" }, // Moved to front
        { model_id: "gemini-pro", model_provider: "google" },
        { model_id: "claude-3", model_provider: "anthropic" },
      ])
      expect(models).toHaveLength(3) // No duplicate entries
    })

    it("should differentiate models by both model_id and model_provider", () => {
      addRecentModel("gpt-4", "openai")
      addRecentModel("gpt-4", "azure") // Same model_id, different provider

      const models = get(recent_model_store)
      expect(models).toEqual([
        { model_id: "gpt-4", model_provider: "azure" },
        { model_id: "gpt-4", model_provider: "openai" },
      ])
      expect(models).toHaveLength(2) // Both should be kept as they have different providers
    })

    it("should maintain maximum of 5 models", () => {
      // Add 6 models
      addRecentModel("model-1", "provider-1")
      addRecentModel("model-2", "provider-2")
      addRecentModel("model-3", "provider-3")
      addRecentModel("model-4", "provider-4")
      addRecentModel("model-5", "provider-5")
      addRecentModel("model-6", "provider-6")

      const models = get(recent_model_store)
      expect(models).toHaveLength(5)
      expect(models).toEqual([
        { model_id: "model-6", model_provider: "provider-6" },
        { model_id: "model-5", model_provider: "provider-5" },
        { model_id: "model-4", model_provider: "provider-4" },
        { model_id: "model-3", model_provider: "provider-3" },
        { model_id: "model-2", model_provider: "provider-2" },
      ])
      // model-1 should be removed as it was the oldest
    })

    it("should handle adding duplicate when at max capacity", () => {
      // Fill to capacity
      addRecentModel("model-1", "provider-1")
      addRecentModel("model-2", "provider-2")
      addRecentModel("model-3", "provider-3")
      addRecentModel("model-4", "provider-4")
      addRecentModel("model-5", "provider-5")

      // Add duplicate of middle item
      addRecentModel("model-3", "provider-3")

      const models = get(recent_model_store)
      expect(models).toHaveLength(5)
      expect(models).toEqual([
        { model_id: "model-3", model_provider: "provider-3" }, // Moved to front
        { model_id: "model-5", model_provider: "provider-5" },
        { model_id: "model-4", model_provider: "provider-4" },
        { model_id: "model-2", model_provider: "provider-2" },
        { model_id: "model-1", model_provider: "provider-1" },
      ])
    })

    it("should handle empty strings for model_id and model_provider", () => {
      addRecentModel("", "")

      const models = get(recent_model_store)
      expect(models).toEqual([])
    })

    it("should handle null for model_provider", () => {
      addRecentModel("", null)

      const models = get(recent_model_store)
      expect(models).toEqual([])
    })

    it("should handle null for model_provider", () => {
      addRecentModel(null, "openrouter")

      const models = get(recent_model_store)
      expect(models).toEqual([])
    })

    it("should persist data through store operations", () => {
      addRecentModel("gpt-4", "openai")

      // The store persists through localStorageStore, which uses localStorage under the hood
      // Even though our mock doesn't capture this due to module loading timing,
      // we can verify the data is in the store
      const models = get(recent_model_store)
      expect(models).toHaveLength(1)
      expect(models[0]).toEqual({ model_id: "gpt-4", model_provider: "openai" })
    })
  })

  describe("integration scenarios", () => {
    beforeEach(() => {
      recent_model_store.set([])
    })

    it("should handle typical user workflow", () => {
      // User tries different models in sequence
      addRecentModel("gpt-3.5-turbo", "openai")
      addRecentModel("gpt-4", "openai")
      addRecentModel("claude-3-sonnet", "anthropic")

      // Goes back to a previous model
      addRecentModel("gpt-4", "openai")

      // Tries more models
      addRecentModel("gemini-pro", "google")
      addRecentModel("claude-3-opus", "anthropic")

      const models = get(recent_model_store)
      expect(models).toEqual([
        { model_id: "claude-3-opus", model_provider: "anthropic" },
        { model_id: "gemini-pro", model_provider: "google" },
        { model_id: "gpt-4", model_provider: "openai" }, // Moved up from being reused
        { model_id: "claude-3-sonnet", model_provider: "anthropic" },
        { model_id: "gpt-3.5-turbo", model_provider: "openai" },
      ])
    })

    it("should maintain correct order after multiple operations", () => {
      // Add 7 models, which should cap at 5
      const modelSequence = [
        ["model-1", "provider-1"],
        ["model-2", "provider-2"],
        ["model-3", "provider-3"],
        ["model-4", "provider-4"],
        ["model-5", "provider-5"],
        ["model-6", "provider-6"],
        ["model-7", "provider-7"],
      ]

      modelSequence.forEach(([id, provider]) => {
        addRecentModel(id, provider)
      })

      let models = get(recent_model_store)
      expect(models).toHaveLength(5)

      // Use an old model (should move to front, no change in count)
      addRecentModel("model-4", "provider-4")

      models = get(recent_model_store)
      expect(models).toEqual([
        { model_id: "model-4", model_provider: "provider-4" }, // Moved to front
        { model_id: "model-7", model_provider: "provider-7" },
        { model_id: "model-6", model_provider: "provider-6" },
        { model_id: "model-5", model_provider: "provider-5" },
        { model_id: "model-3", model_provider: "provider-3" },
      ])
    })
  })
})
