// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

vi.mock("$lib/git_sync/api", () => ({
  renameClone: vi.fn().mockResolvedValue({
    success: true,
    new_clone_path: "/tmp/proj_1 - My Project",
    message: "OK",
  }),
  saveConfig: vi.fn().mockResolvedValue({}),
  is_stale_clone_error: vi.fn().mockReturnValue(false),
  is_duplicate_project_error: vi.fn().mockReturnValue(false),
  isGitHubUrl: () => true,
  isGitLabUrl: () => false,
  GitSyncRequestError: class extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = "GitSyncRequestError"
      this.status = status
    }
  },
}))

vi.mock("$lib/stores/git_import_wizard_store", () => ({
  clear_wizard_store: vi.fn(),
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("$lib/stores", () => ({
  load_projects: vi.fn().mockResolvedValue(undefined),
}))

import StepComplete from "./step_complete.svelte"
import {
  saveConfig,
  is_duplicate_project_error,
  GitSyncRequestError,
} from "$lib/git_sync/api"

const baseProps = {
  git_url: "https://github.com/org/repo.git",
  pat_token: "token",
  oauth_token: null,
  auth_mode: "pat_token",
  clone_path: "/tmp/clone_abc",
  branch: "main",
  project_path: "project.kiln",
  project_id: "proj_1",
  project_name: "My Project",
  on_complete: vi.fn(),
  on_back: vi.fn(),
}

const saveConfigResponse = {
  sync_mode: "auto",
  auth_mode: "pat_token",
  remote_name: "origin",
  branch: "main",
  clone_path: "/tmp/clone",
  git_url: "https://github.com/org/repo.git",
  has_pat_token: true,
  has_oauth_token: false,
}

beforeEach(() => {
  vi.mocked(saveConfig).mockResolvedValue(saveConfigResponse)
  vi.mocked(is_duplicate_project_error).mockReturnValue(false)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("StepComplete", () => {
  it("renders saving spinner as initial state", () => {
    const { container } = render(StepComplete, { props: baseProps })
    expect(container.textContent).toContain("Saving configuration...")
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
  })

  it("renders component without errors", () => {
    const { container } = render(StepComplete, { props: baseProps })
    expect(container).toBeTruthy()
  })

  // Svelte 4 async onMount callbacks do not execute in jsdom/vitest, so we
  // cannot test the automatic rename->save flow triggered on mount. Instead
  // we call the component's exported `run_save` directly to exercise the
  // conflict-detection, retry, and success/error rendering paths. The
  // underlying helpers (GitSyncRequestError, is_duplicate_project_error,
  // saveConfig with remove_conflicting_id) are thoroughly unit-tested in
  // api.test.ts (13+ tests).

  it("run_save success transitions to done state", async () => {
    const { container, component } = render(StepComplete, {
      props: baseProps,
    })

    await component.run_save(false)
    await tick()

    expect(container.textContent).toContain("Git Auto Sync Enabled")
    expect(vi.mocked(saveConfig)).toHaveBeenCalledWith(
      expect.objectContaining({ remove_conflicting_id: false }),
    )
  })

  it("run_save error shows Setup Error", async () => {
    vi.mocked(saveConfig).mockRejectedValueOnce(new Error("Server error"))

    const { container, component } = render(StepComplete, {
      props: baseProps,
    })

    await component.run_save(false)
    await tick()

    expect(container.textContent).toContain("Setup Error")
  })

  it("run_save 409 conflict shows conflict button, click retries with remove_conflicting_id: true", async () => {
    const conflictError = new GitSyncRequestError("Duplicate project ID", 409)
    vi.mocked(saveConfig).mockRejectedValueOnce(conflictError)
    vi.mocked(is_duplicate_project_error).mockReturnValueOnce(true)

    const { container, component, getByText } = render(StepComplete, {
      props: baseProps,
    })

    // First call: triggers 409 conflict
    await component.run_save(false)
    await tick()

    // Verify conflict UI appears
    expect(container.textContent).toContain("Setup Error")
    expect(container.textContent).toContain("Remove existing and sync")

    // Set up the retry to succeed
    vi.mocked(saveConfig).mockResolvedValueOnce(saveConfigResponse)
    vi.mocked(is_duplicate_project_error).mockReturnValue(false)

    // Click the conflict-recovery button
    const retryButton = getByText("Remove existing and sync")
    await fireEvent.click(retryButton)
    // Allow the async run_save promise to settle
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Verify saveConfig was called with remove_conflicting_id: true
    const calls = vi.mocked(saveConfig).mock.calls
    expect(calls.length).toBe(2)
    expect(calls[1][0].remove_conflicting_id).toBe(true)

    // After successful retry, should show success state
    expect(container.textContent).toContain("Git Auto Sync Enabled")
  })

  it("non-409 error does not show conflict button", async () => {
    vi.mocked(saveConfig).mockRejectedValueOnce(new Error("Internal error"))
    vi.mocked(is_duplicate_project_error).mockReturnValue(false)

    const { container, component } = render(StepComplete, {
      props: baseProps,
    })

    await component.run_save(false)
    await tick()

    expect(container.textContent).toContain("Setup Error")
    expect(container.textContent).not.toContain("Remove existing and sync")
  })
})
