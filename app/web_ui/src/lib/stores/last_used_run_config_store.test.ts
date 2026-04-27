import { get } from "svelte/store"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { get_task_composite_id } from "$lib/stores"
import {
  last_used_run_config_store,
  get_last_used_run_config,
  set_last_used_run_config,
} from "./last_used_run_config_store"

const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
}

describe("last_used_run_config_store", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("window", { localStorage: localStorageMock })
    localStorageMock.getItem.mockReturnValue(null)
    localStorageMock.setItem.mockImplementation(() => {})
    last_used_run_config_store.set({})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  const task_a = get_task_composite_id("p1", "t1")
  const task_b = get_task_composite_id("p1", "t2")

  describe("get_last_used_run_config", () => {
    it("returns null when no value has been saved", () => {
      expect(get_last_used_run_config(task_a)).toBeNull()
    })

    it("returns the saved value after set", () => {
      set_last_used_run_config(task_a, "run-config-1")
      expect(get_last_used_run_config(task_a)).toBe("run-config-1")
    })

    it("returns 'custom' when saved as custom", () => {
      set_last_used_run_config(task_a, "custom")
      expect(get_last_used_run_config(task_a)).toBe("custom")
    })

    it("keeps per-task values isolated", () => {
      set_last_used_run_config(task_a, "run-config-1")
      set_last_used_run_config(task_b, "custom")
      expect(get_last_used_run_config(task_a)).toBe("run-config-1")
      expect(get_last_used_run_config(task_b)).toBe("custom")
    })
  })

  describe("set_last_used_run_config", () => {
    it("overwrites the previous value for the same task", () => {
      set_last_used_run_config(task_a, "run-config-1")
      set_last_used_run_config(task_a, "run-config-2")
      expect(get_last_used_run_config(task_a)).toBe("run-config-2")
    })

    it("removes the entry when value is null", () => {
      set_last_used_run_config(task_a, "run-config-1")
      set_last_used_run_config(task_a, null)
      expect(get_last_used_run_config(task_a)).toBeNull()
      expect(task_a in get(last_used_run_config_store)).toBe(false)
    })

    it("is a no-op when setting null for an unknown task", () => {
      set_last_used_run_config(task_a, null)
      expect(get(last_used_run_config_store)).toEqual({})
    })

    it("is a no-op when setting the same value again", () => {
      set_last_used_run_config(task_a, "run-config-1")
      const before = get(last_used_run_config_store)
      set_last_used_run_config(task_a, "run-config-1")
      const after = get(last_used_run_config_store)
      expect(after).toBe(before)
    })
  })
})
