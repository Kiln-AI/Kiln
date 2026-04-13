import { oauthStart, oauthStatus } from "$lib/git_sync/api"
import type { OAuthStartResponse } from "$lib/git_sync/api"

const POLL_INTERVAL_MS = 2000
const TIMEOUT_MS = 300_000
const MAX_CONSECUTIVE_POLL_FAILURES = 5
// When GitHub's org or repo couldn't be pre-selected, the component renders
// a hint telling the user what to pick on GitHub. Delay popup navigation so
// the hint is visible in Kiln before GitHub's tab steals focus.
const HINT_DISPLAY_DELAY_MS = 1500

export type OAuthFlowCallbacks = {
  onStarted: (response: OAuthStartResponse) => void
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
    // Close popup on cancel/timeout, but not on success (HTML_SUCCESS page
    // self-closes via its own script — calling close() again from a different
    // origin after navigation may be blocked).
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
    // popup blockers. We'll navigate it to the install URL once the API responds.
    // If this returns null, the popup was blocked — surface an error rather
    // than trying to re-open later (which would also be blocked since it runs
    // after an await, outside the user gesture).
    // Callers may pass a pre-opened popup to ensure window.open is at the
    // very top of the click handler (Safari is strict about user gestures
    // even with synchronous async function bodies).
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

    let startResponse: OAuthStartResponse
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

    callbacks.onStarted(startResponse)

    // If Kiln needs to show the user a pre-selection hint (because we
    // couldn't pre-fill the org or repo on GitHub's install page), pause
    // briefly so the hint renders before the popup takes focus.
    const needsHint =
      !startResponse.owner_pre_selected || !startResponse.repo_pre_selected
    if (needsHint) {
      await new Promise((resolve) => setTimeout(resolve, HINT_DISPLAY_DELAY_MS))
      if (cancelled) {
        cleanup(true)
        return
      }
    }

    // Navigate the popup to the install URL. For new users, GitHub chains:
    // install → setup URL redirect → OAuth authorize → callback.
    // For returning users who already have the app installed, the install
    // page shows a "manage" view with no redirect. The component provides
    // an escape hatch link to authorize directly for that case.
    popup.location.href = startResponse.install_url
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
