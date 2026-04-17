import { oauthStart, oauthStatus } from "$lib/git_sync/api"

const POLL_INTERVAL_MS = 2000
const TIMEOUT_MS = 300_000
const MAX_CONSECUTIVE_POLL_FAILURES = 5

export type OAuthFlowCallbacks = {
  onStarted: (response: { install_url: string }) => void
  onPolling: () => void
  onSuccess: (token: string) => void
  onError: (error: string) => void
}

export function startOAuthFlow(
  git_url: string,
  callbacks: OAuthFlowCallbacks,
  preOpenedPopup?: Window | null,
): { cancel: () => void } {
  let cancelled = false
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null
  let popup: Window | null = preOpenedPopup ?? null

  function cleanup(closePopup: boolean = false) {
    cancelled = true
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    if (timeoutTimer !== null) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
    if (closePopup && popup !== null) {
      try {
        popup.close()
      } catch {
        // Ignore — window may already be closed or cross-origin.
      }
      popup = null
    }
  }

  async function run() {
    // Open the window synchronously (during the user's click event) to avoid
    // popup blockers. Callers may pass a pre-opened popup to ensure
    // window.open is at the very top of the click handler (Safari is strict
    // about user gestures even with synchronous async function bodies).
    if (popup === null) {
      popup = window.open("about:blank", "_blank")
    }

    if (!popup) {
      if (!cancelled) {
        cleanup(false)
        callbacks.onError(
          "Popup blocked. Please allow popups for this site and try again.",
        )
      }
      return
    }

    let startResponse
    try {
      startResponse = await oauthStart(git_url)
    } catch (e) {
      if (!cancelled) {
        cleanup(true)
        callbacks.onError(
          e instanceof Error ? e.message : "Failed to start OAuth flow",
        )
      }
      return
    }

    if (cancelled) {
      cleanup(true)
      return
    }

    // Provide the install_url so the caller can offer an "Install app" step
    // if the token doesn't have access after authorization.
    callbacks.onStarted({ install_url: startResponse.install_url })

    // Navigate the popup directly to the OAuth authorize URL.
    // This is always a consistent flow regardless of app installation state.
    popup.location.href = startResponse.authorize_url
    callbacks.onPolling()

    const state = startResponse.state

    timeoutTimer = setTimeout(() => {
      if (!cancelled) {
        cleanup(true)
        callbacks.onError("Authorization timed out. Please try again.")
      }
    }, TIMEOUT_MS)

    let consecutivePollFailures = 0

    async function poll() {
      if (cancelled) return
      try {
        const status = await oauthStatus(state)
        if (cancelled) return
        consecutivePollFailures = 0

        if (status.complete && status.oauth_token) {
          cleanup()
          callbacks.onSuccess(status.oauth_token)
        } else if (status.error) {
          cleanup()
          callbacks.onError(status.error)
        } else {
          pollTimer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (e) {
        if (cancelled) return
        consecutivePollFailures++
        console.warn("OAuth status polling network error:", e)
        if (consecutivePollFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
          const reason = e instanceof Error ? e.message : "connection failed"
          cleanup(true)
          callbacks.onError(
            `Couldn't check GitHub authorization status (${reason}). Please try again.`,
          )
          return
        }
        pollTimer = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    poll()
  }

  run()

  return { cancel: () => cleanup(true) }
}
