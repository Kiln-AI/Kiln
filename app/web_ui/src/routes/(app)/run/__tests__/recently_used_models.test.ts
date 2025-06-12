// Mock localStorage for vitest/node environment
if (typeof globalThis.localStorage === "undefined") {
  let store: Record<string, string> = {}
  globalThis.localStorage = {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
    key: (i: number) => Object.keys(store)[i] || null,
    get length() {
      return Object.keys(store).length
    },
  }
}

import { describe, it, expect, beforeEach } from "vitest"
import { get } from "svelte/store"
import {
  ui_state,
  recently_used_models,
  add_recently_used_model,
  _recently_used_models_test_only,
} from "$lib/stores"

describe("Recently Used Models", () => {
  beforeEach(() => {
    // Reset stores before each test
    ui_state.update(() => ({
      current_project_id: null,
      current_task_id: null,
      selected_model: null,
    }))
    // Reset recently_used_models by setting it to an empty object
    _recently_used_models_test_only.set({})
  })

  it("should add a model to recently used models", () => {
    // Set current project and task
    ui_state.update((state) => ({
      ...state,
      current_project_id: "project1",
      current_task_id: "task1",
    }))

    // Add a model
    add_recently_used_model("openai/gpt-4")

    // Get the current state
    const currentState = get(recently_used_models)
    const key = "project1/task1"

    // Verify the model was added
    expect(currentState[key]).toBeDefined()
    expect(currentState[key]).toContain("openai/gpt-4")
  })

  it("should move model to front when added again", () => {
    // Set current project and task
    ui_state.update((state) => ({
      ...state,
      current_project_id: "project1",
      current_task_id: "task1",
    }))

    // Add models in sequence
    add_recently_used_model("openai/gpt-3.5")
    add_recently_used_model("openai/gpt-4")
    add_recently_used_model("openai/gpt-3.5") // Add again

    // Get the current state
    const currentState = get(recently_used_models)
    const key = "project1/task1"

    // Verify the model was moved to front
    expect(currentState[key][0]).toBe("openai/gpt-3.5")
    expect(currentState[key][1]).toBe("openai/gpt-4")
  })

  it("should limit to 5 models per project/task", () => {
    // Set current project and task
    ui_state.update((state) => ({
      ...state,
      current_project_id: "project1",
      current_task_id: "task1",
    }))

    // Add 6 models
    add_recently_used_model("provider/model1")
    add_recently_used_model("provider/model2")
    add_recently_used_model("provider/model3")
    add_recently_used_model("provider/model4")
    add_recently_used_model("provider/model5")
    add_recently_used_model("provider/model6")

    // Get the current state
    const currentState = get(recently_used_models)
    const key = "project1/task1"

    // Verify only 5 models are kept
    expect(currentState[key].length).toBe(5)
    expect(currentState[key][0]).toBe("provider/model6") // Most recent
    expect(currentState[key][4]).toBe("provider/model2") // Oldest kept
    expect(currentState[key]).not.toContain("provider/model1") // First one should be removed
  })

  it("should handle different project/task combinations", () => {
    // Add models for different project/task combinations
    ui_state.update((state) => ({
      ...state,
      current_project_id: "project1",
      current_task_id: "task1",
    }))
    add_recently_used_model("provider/model1")

    ui_state.update((state) => ({
      ...state,
      current_project_id: "project1",
      current_task_id: "task2",
    }))
    add_recently_used_model("provider/model2")

    ui_state.update((state) => ({
      ...state,
      current_project_id: "project2",
      current_task_id: "task1",
    }))
    add_recently_used_model("provider/model3")

    // Get the current state
    const currentState = get(recently_used_models)

    // Verify each project/task combination has its own list
    expect(currentState["project1/task1"]).toContain("provider/model1")
    expect(currentState["project1/task2"]).toContain("provider/model2")
    expect(currentState["project2/task1"]).toContain("provider/model3")
  })

  it("should handle null project or task ID", () => {
    // Set null project and task
    ui_state.update((state) => ({
      ...state,
      current_project_id: null,
      current_task_id: null,
    }))

    // Add a model
    add_recently_used_model("model1")

    // Get the current state
    const currentState = get(recently_used_models)

    // Verify no models were added
    expect(Object.keys(currentState).length).toBe(0)
  })
})
