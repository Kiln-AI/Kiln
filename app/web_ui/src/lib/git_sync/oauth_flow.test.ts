import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { startOAuthFlow, type OAuthFlowCallbacks } from "./oauth_flow"
import type { OAuthStartResponse } from "./api"

vi.mock("$lib/git_sync/api", () => ({
  oauthStart: vi.fn(),
  oauthStatus: vi.fn(),
}))

import { oauthStart, oauthStatus } from "$lib/git_sync/api"

const mockOauthStart = vi.mocked(oauthStart)
const mockOauthStatus = vi.mocked(oauthStatus)

function makeCallbacks(): OAuthFlowCallbacks & {
  calls: Record<string, unknown[]>
} {
  const calls: Record<string, unknown[]> = {
    onStarted: [],
    onPolling: [],
    onSuccess: [],
    onError: [],
  }
  return {
    calls,
    onStarted: (response) => calls.onStarted.push(response),
    onPolling: () => calls.onPolling.push(true),
    onSuccess: (token) => calls.onSuccess.push(token),
    onError: (error) => calls.onError.push(error),
  }
}

const MOCK_START_RESPONSE: OAuthStartResponse = {
  authorize_url:
    "https://github.com/login/oauth/authorize?client_id=test&state=test_state_123",
  install_url: "https://github.com/apps/kiln-ai/installations/new",
  state: "test_state_123",
  owner_name: "Kiln-AI",
  repo_name: "kiln",
  owner_pre_selected: true,
  repo_pre_selected: false,
}

function makeMockPopup() {
  return {
    location: { href: "" },
    close: vi.fn(),
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  mockOauthStart.mockReset()
  mockOauthStatus.mockReset()
  const mockWindow = { open: vi.fn(() => makeMockPopup()) }
  vi.stubGlobal("window", mockWindow)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe("startOAuthFlow", () => {
  it("calls oauthStart and opens install URL in browser", async () => {
    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)
    mockOauthStatus.mockResolvedValue({
      complete: false,
      oauth_token: null,
      error: null,
    })

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)

    expect(mockOauthStart).toHaveBeenCalledWith(
      "https://github.com/Kiln-AI/kiln.git",
    )
    expect(cbs.calls.onStarted).toHaveLength(1)
    expect(cbs.calls.onStarted[0]).toEqual(MOCK_START_RESPONSE)
    expect(cbs.calls.onPolling).toHaveLength(1)
    // The first window.open is about:blank (popup), then location.href is set
    expect(window.open).toHaveBeenCalledWith("about:blank", "_blank")
  })

  it("calls onSuccess when polling returns a token", async () => {
    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)
    mockOauthStatus
      .mockResolvedValueOnce({
        complete: false,
        oauth_token: null,
        error: null,
      })
      .mockResolvedValueOnce({
        complete: true,
        oauth_token: "ghu_abc123",
        error: null,
      })

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)
    expect(mockOauthStatus).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2000)
    expect(mockOauthStatus).toHaveBeenCalledTimes(2)

    expect(cbs.calls.onSuccess).toHaveLength(1)
    expect(cbs.calls.onSuccess[0]).toBe("ghu_abc123")
  })

  it("calls onError when polling returns an error", async () => {
    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)
    mockOauthStatus
      .mockResolvedValueOnce({
        complete: false,
        oauth_token: null,
        error: null,
      })
      .mockResolvedValueOnce({
        complete: false,
        oauth_token: null,
        error: "access_denied",
      })

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2000)

    expect(cbs.calls.onError).toHaveLength(1)
    expect(cbs.calls.onError[0]).toBe("access_denied")
  })

  it("calls onError on start failure", async () => {
    mockOauthStart.mockRejectedValue(new Error("Network error"))

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)

    expect(cbs.calls.onError).toHaveLength(1)
    expect(cbs.calls.onError[0]).toBe("Network error")
  })

  it("stops polling and closes popup on cancel", async () => {
    const popup = makeMockPopup()
    const mockWindow = { open: vi.fn(() => popup) }
    vi.stubGlobal("window", mockWindow)

    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)
    mockOauthStatus.mockResolvedValue({
      complete: false,
      oauth_token: null,
      error: null,
    })

    const cbs = makeCallbacks()
    const handle = startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)
    expect(mockOauthStatus).toHaveBeenCalledTimes(1)

    handle.cancel()

    await vi.advanceTimersByTimeAsync(10000)
    expect(mockOauthStatus).toHaveBeenCalledTimes(1)
    expect(popup.close).toHaveBeenCalled()
  })

  it("times out and closes popup after 5 minutes", async () => {
    const popup = makeMockPopup()
    const mockWindow = { open: vi.fn(() => popup) }
    vi.stubGlobal("window", mockWindow)

    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)
    mockOauthStatus.mockResolvedValue({
      complete: false,
      oauth_token: null,
      error: null,
    })

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)

    await vi.advanceTimersByTimeAsync(300_000)

    expect(cbs.calls.onError).toHaveLength(1)
    expect(cbs.calls.onError[0]).toContain("timed out")
    expect(popup.close).toHaveBeenCalled()
  })

  it("calls onError when popup is blocked", async () => {
    const mockWindow = { open: vi.fn(() => null) }
    vi.stubGlobal("window", mockWindow)
    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)

    expect(cbs.calls.onError).toHaveLength(1)
    expect(cbs.calls.onError[0]).toContain("Popup blocked")
    expect(mockOauthStart).not.toHaveBeenCalled()
  })

  it("retries polling on network error during status check", async () => {
    mockOauthStart.mockResolvedValue(MOCK_START_RESPONSE)
    mockOauthStatus
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValueOnce({
        complete: true,
        oauth_token: "ghu_recovered",
        error: null,
      })

    const cbs = makeCallbacks()
    startOAuthFlow("https://github.com/Kiln-AI/kiln.git", cbs)

    await vi.advanceTimersByTimeAsync(0)
    expect(mockOauthStatus).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2000)
    expect(mockOauthStatus).toHaveBeenCalledTimes(2)
    expect(cbs.calls.onSuccess).toHaveLength(1)
    expect(cbs.calls.onSuccess[0]).toBe("ghu_recovered")
  })
})
