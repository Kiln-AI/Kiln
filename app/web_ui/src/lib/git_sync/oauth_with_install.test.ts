import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import { createOAuthWithInstall } from "./oauth_with_install"

vi.mock("$lib/git_sync/api", () => ({
  testAccess: vi.fn(),
}))

vi.mock("$lib/git_sync/oauth_flow", () => ({
  startOAuthFlow: vi.fn(),
}))

import { testAccess } from "$lib/git_sync/api"
import { startOAuthFlow } from "$lib/git_sync/oauth_flow"

const mockTestAccess = vi.mocked(testAccess)
const mockStartOAuthFlow = vi.mocked(startOAuthFlow)

beforeEach(() => {
  mockTestAccess.mockReset()
  mockStartOAuthFlow.mockReset()
  const mockWindow = {
    open: vi.fn(() => ({ location: { href: "" }, close: vi.fn() })),
  }
  vi.stubGlobal("window", mockWindow)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function setupStartOAuthFlow() {
  let capturedCallbacks: Parameters<typeof startOAuthFlow>[1] | null = null
  const cancelFn = vi.fn()
  mockStartOAuthFlow.mockImplementation((_url, callbacks, _popup) => {
    capturedCallbacks = callbacks
    return { cancel: cancelFn }
  })
  return {
    getCallbacks: () => capturedCallbacks!,
    cancelFn,
  }
}

describe("createOAuthWithInstall", () => {
  it("starts in initial state", () => {
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    const state = get(flow.state)
    expect(state.oauth_starting).toBe(false)
    expect(state.oauth_error).toBeNull()
    expect(state.checking_access).toBe(false)
    expect(state.needs_install).toBe(false)
    expect(state.install_url).toBeNull()
    expect(state.install_clicked).toBe(false)
  })

  it("sets oauth_starting on start()", () => {
    setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()
    expect(get(flow.state).oauth_starting).toBe(true)
    expect(mockStartOAuthFlow).toHaveBeenCalledWith(
      "https://github.com/org/repo.git",
      expect.any(Object),
      expect.anything(),
    )
  })

  it("clears oauth_starting and stores install_url on onStarted", () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()
    getCallbacks().onStarted({
      install_url: "https://github.com/apps/kiln/installations/new",
    })
    const state = get(flow.state)
    expect(state.oauth_starting).toBe(false)
    expect(state.install_url).toBe(
      "https://github.com/apps/kiln/installations/new",
    )
  })

  it("calls on_success when access check succeeds after OAuth token", async () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const onSuccess = vi.fn()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: onSuccess,
    })
    flow.start()

    mockTestAccess.mockResolvedValueOnce({
      success: true,
      message: "",
      auth_required: false,
      auth_method: "github_oauth",
    })

    getCallbacks().onSuccess("ghu_token123")
    await vi.waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith("ghu_token123")
    })
  })

  it("transitions to needs_install when access check fails", async () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const onSuccess = vi.fn()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: onSuccess,
    })
    flow.start()

    mockTestAccess.mockResolvedValueOnce({
      success: false,
      message: "No access",
      auth_required: true,
      auth_method: null,
    })

    getCallbacks().onSuccess("ghu_token123")
    await vi.waitFor(() => {
      expect(get(flow.state).needs_install).toBe(true)
    })
    expect(get(flow.state).checking_access).toBe(false)
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it("sets oauth_error when access check throws", async () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()

    mockTestAccess.mockRejectedValueOnce(new Error("Network failure"))

    getCallbacks().onSuccess("ghu_token123")
    await vi.waitFor(() => {
      expect(get(flow.state).oauth_error).toBe("Network failure")
    })
  })

  it("sets oauth_error on OAuth flow error", () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()
    getCallbacks().onError("access_denied")
    expect(get(flow.state).oauth_error).toBe("access_denied")
    expect(get(flow.state).oauth_starting).toBe(false)
  })

  it("resets all state on reset()", () => {
    const { getCallbacks, cancelFn } = setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()
    getCallbacks().onError("some error")
    expect(get(flow.state).oauth_error).toBe("some error")

    flow.reset()
    const state = get(flow.state)
    expect(state.oauth_starting).toBe(false)
    expect(state.oauth_error).toBeNull()
    expect(state.needs_install).toBe(false)
    expect(state.install_url).toBeNull()
    expect(state.install_clicked).toBe(false)
    expect(state.checking_access).toBe(false)
    expect(cancelFn).toHaveBeenCalled()
  })

  it("ignores stale callbacks after reset (generation tracking)", async () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const onSuccess = vi.fn()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: onSuccess,
    })
    flow.start()
    const staleCallbacks = getCallbacks()

    flow.reset()

    mockTestAccess.mockResolvedValueOnce({
      success: true,
      message: "",
      auth_required: false,
      auth_method: "github_oauth",
    })
    staleCallbacks.onSuccess("ghu_stale_token")
    await new Promise((r) => setTimeout(r, 10))

    expect(onSuccess).not.toHaveBeenCalled()
    expect(get(flow.state).checking_access).toBe(false)
  })

  it("ignores stale callbacks after start() is called again", async () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const onSuccess = vi.fn()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: onSuccess,
    })
    flow.start()
    const firstCallbacks = getCallbacks()

    flow.start()

    mockTestAccess.mockResolvedValueOnce({
      success: true,
      message: "",
      auth_required: false,
      auth_method: "github_oauth",
    })
    firstCallbacks.onSuccess("ghu_stale")
    await new Promise((r) => setTimeout(r, 10))
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it("open_install opens window and sets install_clicked", () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()
    getCallbacks().onStarted({
      install_url: "https://github.com/apps/kiln/installations/new",
    })

    flow.open_install()
    expect(window.open).toHaveBeenCalledWith(
      "https://github.com/apps/kiln/installations/new",
      "_blank",
      "noopener,noreferrer",
    )
    expect(get(flow.state).install_clicked).toBe(true)
  })

  it("verify_access re-checks and calls on_success", async () => {
    const { getCallbacks } = setupStartOAuthFlow()
    const onSuccess = vi.fn()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: onSuccess,
    })
    flow.start()

    mockTestAccess.mockResolvedValueOnce({
      success: false,
      message: "No access",
      auth_required: true,
      auth_method: null,
    })
    getCallbacks().onSuccess("ghu_token123")
    await vi.waitFor(() => {
      expect(get(flow.state).needs_install).toBe(true)
    })

    mockTestAccess.mockResolvedValueOnce({
      success: true,
      message: "",
      auth_required: false,
      auth_method: "github_oauth",
    })
    await flow.verify_access()
    expect(onSuccess).toHaveBeenCalledWith("ghu_token123")
  })

  it("verify_access is a no-op when no token has been stored", async () => {
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    await flow.verify_access()
    expect(mockTestAccess).not.toHaveBeenCalled()
    const state = get(flow.state)
    expect(state.checking_access).toBe(false)
    expect(state.oauth_error).toBeNull()
  })

  it("destroy cancels active flow", () => {
    const { cancelFn } = setupStartOAuthFlow()
    const flow = createOAuthWithInstall({
      git_url: "https://github.com/org/repo.git",
      on_success: vi.fn(),
    })
    flow.start()
    flow.destroy()
    expect(cancelFn).toHaveBeenCalled()
  })
})
