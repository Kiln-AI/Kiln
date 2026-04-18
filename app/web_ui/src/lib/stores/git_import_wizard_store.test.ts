import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"

function stubStorage() {
  const store: Record<string, string> = {}
  return {
    store,
    mock: {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key]
      }),
    },
  }
}

describe("git_import_wizard_store", () => {
  let storage: ReturnType<typeof stubStorage>

  beforeEach(() => {
    storage = stubStorage()
    vi.stubGlobal("window", {
      sessionStorage: storage.mock,
    })
    vi.stubGlobal("sessionStorage", storage.mock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  async function importFresh() {
    return await import("./git_import_wizard_store")
  }

  it("initializes with default empty state", async () => {
    const mod = await importFresh()
    const state = get(mod.git_import_wizard_store)
    expect(state.git_url).toBe("")
    expect(state.pat_token).toBeNull()
    expect(state.auth_mode).toBe("system_keys")
    expect(state.clone_path).toBe("")
    expect(state.selected_branch).toBe("")
    expect(state.selected_project_path).toBe("")
    expect(state.selected_project_id).toBe("")
    expect(state.selected_project_name).toBe("")
  })

  it("persists state updates to sessionStorage", async () => {
    const mod = await importFresh()
    mod.git_import_wizard_store.update((s) => ({
      ...s,
      git_url: "https://github.com/test/repo",
    }))
    const stored = JSON.parse(storage.store["git_import_wizard"])
    expect(stored.git_url).toBe("https://github.com/test/repo")
  })

  it("restores state from sessionStorage", async () => {
    storage.store["git_import_wizard"] = JSON.stringify({
      git_url: "https://github.com/restored/repo",
      pat_token: "ghp_test",
      auth_mode: "pat_token",
      clone_path: "/tmp/clone",
      selected_branch: "main",
      selected_project_path: "project.kiln",
      selected_project_id: "id123",
      selected_project_name: "My Project",
    })
    const mod = await importFresh()
    const state = get(mod.git_import_wizard_store)
    expect(state.git_url).toBe("https://github.com/restored/repo")
    expect(state.pat_token).toBe("ghp_test")
    expect(state.clone_path).toBe("/tmp/clone")
    expect(state.selected_branch).toBe("main")
  })

  it("clear_wizard_store resets to defaults", async () => {
    const mod = await importFresh()
    mod.git_import_wizard_store.update((s) => ({
      ...s,
      git_url: "https://github.com/test/repo",
      pat_token: "ghp_secret",
      clone_path: "/tmp/clone",
    }))
    mod.clear_wizard_store()
    const state = get(mod.git_import_wizard_store)
    expect(state.git_url).toBe("")
    expect(state.pat_token).toBeNull()
    expect(state.clone_path).toBe("")
  })

  describe("validate_step_requirements", () => {
    it("allows method, local_file, and url steps unconditionally", async () => {
      const mod = await importFresh()
      expect(mod.validate_step_requirements("method")).toBe(true)
      expect(mod.validate_step_requirements("local_file")).toBe(true)
      expect(mod.validate_step_requirements("url")).toBe(true)
    })

    it("requires git_url for credentials step", async () => {
      const mod = await importFresh()
      expect(mod.validate_step_requirements("credentials")).toBe(false)
      mod.git_import_wizard_store.update((s) => ({
        ...s,
        git_url: "https://github.com/test/repo",
      }))
      expect(mod.validate_step_requirements("credentials")).toBe(true)
    })

    it("requires git_url for branch step", async () => {
      const mod = await importFresh()
      expect(mod.validate_step_requirements("branch")).toBe(false)
      mod.git_import_wizard_store.update((s) => ({
        ...s,
        git_url: "https://github.com/test/repo",
      }))
      expect(mod.validate_step_requirements("branch")).toBe(true)
    })

    it("requires pat_token for branch step when auth_mode is pat_token", async () => {
      const mod = await importFresh()
      mod.git_import_wizard_store.update((s) => ({
        ...s,
        git_url: "https://github.com/test/repo",
        auth_mode: "pat_token",
      }))
      expect(mod.validate_step_requirements("branch")).toBe(false)
      mod.git_import_wizard_store.update((s) => ({
        ...s,
        pat_token: "ghp_test",
      }))
      expect(mod.validate_step_requirements("branch")).toBe(true)
    })

    it("requires clone_path for project step", async () => {
      const mod = await importFresh()
      expect(mod.validate_step_requirements("project")).toBe(false)
      mod.git_import_wizard_store.update((s) => ({
        ...s,
        clone_path: "/tmp/clone",
      }))
      expect(mod.validate_step_requirements("project")).toBe(true)
    })

    it("requires clone_path, selected_branch, and selected_project_path for complete step", async () => {
      const mod = await importFresh()
      expect(mod.validate_step_requirements("complete")).toBe(false)

      mod.git_import_wizard_store.update((s) => ({
        ...s,
        clone_path: "/tmp/clone",
      }))
      expect(mod.validate_step_requirements("complete")).toBe(false)

      mod.git_import_wizard_store.update((s) => ({
        ...s,
        selected_branch: "main",
      }))
      expect(mod.validate_step_requirements("complete")).toBe(false)

      mod.git_import_wizard_store.update((s) => ({
        ...s,
        selected_project_path: "project.kiln",
      }))
      expect(mod.validate_step_requirements("complete")).toBe(true)
    })
  })
})
