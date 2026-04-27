import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import {
  agentInfo,
  getCurrentAppState,
  buildContextHeader,
  formatHeader,
  formatChangedHeader,
  type AppState,
} from "./agent"

vi.mock("$lib/stores", () => {
  const { writable } = require("svelte/store")
  return {
    ui_state: writable({
      current_project_id: null,
      current_task_id: null,
      selected_model: null,
    }),
  }
})

beforeEach(() => {
  agentInfo.set(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("agentInfo store", () => {
  it("starts as null", () => {
    expect(get(agentInfo)).toBeNull()
  })

  it("can be set and read", () => {
    agentInfo.set({ name: "Test Page", description: "A test page" })
    expect(get(agentInfo)).toEqual({
      name: "Test Page",
      description: "A test page",
    })
  })
})

describe("getCurrentAppState", () => {
  it("returns path from window.location.pathname", async () => {
    vi.stubGlobal("window", {
      location: { pathname: "/test/path" },
    })
    const { ui_state } = await import("$lib/stores")
    ui_state.set({
      current_project_id: "proj-1",
      current_task_id: "task-1",
      selected_model: null,
    })
    agentInfo.set({ name: "Test", description: "Desc" })

    const state = getCurrentAppState()
    expect(state.path).toBe("/test/path")
    expect(state.pageName).toBe("Test")
    expect(state.pageDescription).toBe("Desc")
    expect(state.currentProject).toBe("proj-1")
    expect(state.currentTask).toBe("task-1")
  })

  it("returns null for pageName/pageDescription when agentInfo is null", () => {
    vi.stubGlobal("window", {
      location: { pathname: "/some/path" },
    })
    agentInfo.set(null)

    const state = getCurrentAppState()
    expect(state.pageName).toBeNull()
    expect(state.pageDescription).toBeNull()
  })

  it("returns empty path when window is undefined", () => {
    vi.stubGlobal("window", undefined)
    const state = getCurrentAppState()
    expect(state.path).toBe("")
  })
})

describe("formatHeader", () => {
  it("produces correct XML block with all fields", () => {
    const state: AppState = {
      path: "/tools/123",
      pageName: "Tool Detail",
      pageDescription: "Detail page for tool 123",
      currentProject: "proj-1",
      currentTask: "task-1",
    }

    const result = formatHeader(state)
    expect(result).toBe(
      `<new_app_ui_context>\nPath: /tools/123\nPage Name: Tool Detail\nPage Description: Detail page for tool 123\nCurrent Project: proj-1\nCurrent Task: task-1\n</new_app_ui_context>`,
    )
  })

  it("omits null fields", () => {
    const state: AppState = {
      path: "/settings",
      pageName: null,
      pageDescription: null,
      currentProject: null,
      currentTask: null,
    }

    const result = formatHeader(state)
    expect(result).toBe(
      `<new_app_ui_context>\nPath: /settings\n</new_app_ui_context>`,
    )
  })

  it("omits empty string path", () => {
    const state: AppState = {
      path: "",
      pageName: null,
      pageDescription: null,
      currentProject: null,
      currentTask: null,
    }

    const result = formatHeader(state)
    expect(result).toBe("")
  })
})

describe("formatChangedHeader", () => {
  it("produces XML block with only provided fields", () => {
    const result = formatChangedHeader({
      path: "/new/path",
      pageName: "New Page",
    })
    expect(result).toBe(
      `<new_app_ui_context>\nPath: /new/path\nPage Name: New Page\n</new_app_ui_context>`,
    )
  })

  it("represents null values as (none) in changed fields", () => {
    const result = formatChangedHeader({
      path: "/path",
      pageName: null,
    })
    expect(result).toBe(
      `<new_app_ui_context>\nPath: /path\nPage Name: (none)\n</new_app_ui_context>`,
    )
  })
})

describe("buildContextHeader", () => {
  const fullState: AppState = {
    path: "/tools/123",
    pageName: "Tool Detail",
    pageDescription: "Detail page for tool 123",
    currentProject: "proj-1",
    currentTask: "task-1",
  }

  it("returns full header when lastSent is null (first message)", () => {
    const result = buildContextHeader(fullState, null)
    expect(result).toContain("Path: /tools/123")
    expect(result).toContain("Page Name: Tool Detail")
    expect(result).toContain("Page Description: Detail page for tool 123")
    expect(result).toContain("Current Project: proj-1")
    expect(result).toContain("Current Task: task-1")
    expect(result).toMatch(/^<new_app_ui_context>/)
    expect(result).toMatch(/<\/new_app_ui_context>$/)
  })

  it("returns null when nothing changed", () => {
    const result = buildContextHeader(fullState, { ...fullState })
    expect(result).toBeNull()
  })

  it("returns only changed fields on partial change", () => {
    const lastSent: AppState = {
      ...fullState,
      path: "/old/path",
      pageName: "Old Page",
    }

    const result = buildContextHeader(fullState, lastSent)
    expect(result).toContain("Path: /tools/123")
    expect(result).toContain("Page Name: Tool Detail")
    expect(result).not.toContain("Current Project")
    expect(result).not.toContain("Current Task")
  })

  it("omits null fields from output", () => {
    const current: AppState = {
      path: "/settings",
      pageName: null,
      pageDescription: null,
      currentProject: null,
      currentTask: null,
    }

    const result = buildContextHeader(current, null)
    expect(result).toContain("Path: /settings")
    expect(result).not.toContain("Page Name")
    expect(result).not.toContain("Page Description")
    expect(result).not.toContain("Current Project")
    expect(result).not.toContain("Current Task")
  })

  it("includes path when only path changed", () => {
    const lastSent: AppState = {
      ...fullState,
      path: "/old/path",
    }

    const result = buildContextHeader(fullState, lastSent)
    expect(result).toContain("Path: /tools/123")
    expect(result).not.toContain("Page Name")
    expect(result).not.toContain("Current Project")
  })

  it("represents all fields transitioning to null with (none)", () => {
    const current: AppState = {
      path: "",
      pageName: null,
      pageDescription: null,
      currentProject: null,
      currentTask: null,
    }

    const result = buildContextHeader(current, fullState)
    expect(result).not.toBeNull()
    expect(result).toContain("Path: (none)")
    expect(result).toContain("Page Name: (none)")
    expect(result).toContain("Current Project: (none)")
    expect(result).toContain("Current Task: (none)")
  })

  it("detects change from non-null to null", () => {
    const current: AppState = {
      ...fullState,
      currentTask: null,
    }

    const result = buildContextHeader(current, fullState)
    expect(result).not.toBeNull()
    expect(result).toContain("Current Task: (none)")
    expect(result).not.toContain("Path")
  })
})
