import { get, writable, type Readable } from "svelte/store"
import { testAccess } from "$lib/git_sync/api"
import { startOAuthFlow, type OAuthFlowCallbacks } from "./oauth_flow"

export type OAuthWithInstallState = {
  oauth_starting: boolean
  oauth_error: string | null
  checking_access: boolean
  needs_install: boolean
  install_url: string | null
  install_clicked: boolean
  authorize_url: string | null
  popup_blocked: boolean
}

export const INITIAL_STATE: OAuthWithInstallState = {
  oauth_starting: false,
  oauth_error: null,
  checking_access: false,
  needs_install: false,
  install_url: null,
  install_clicked: false,
  authorize_url: null,
  popup_blocked: false,
}

export type OAuthWithInstallOptions = {
  git_url: string
  on_success: (token: string) => void | Promise<void>
}

export type OAuthWithInstallFlow = {
  state: Readable<OAuthWithInstallState>
  start: () => void
  reset: () => void
  open_install: () => void
  verify_access: () => Promise<void>
  destroy: () => void
}

export function createOAuthWithInstall(
  options: OAuthWithInstallOptions,
): OAuthWithInstallFlow {
  const state = writable<OAuthWithInstallState>({ ...INITIAL_STATE })

  let cancel_oauth: (() => void) | null = null
  let generation = 0
  let stored_token: string | null = null

  function update(partial: Partial<OAuthWithInstallState>) {
    state.update((s) => ({ ...s, ...partial }))
  }

  function reset() {
    if (cancel_oauth) {
      cancel_oauth()
      cancel_oauth = null
    }
    stored_token = null
    generation++
    state.set({ ...INITIAL_STATE })
  }

  async function check_access(token: string, gen: number) {
    update({ checking_access: true })
    try {
      const result = await testAccess(
        options.git_url,
        null,
        "github_oauth",
        token,
      )
      if (gen !== generation) return
      if (result.success) {
        await options.on_success(token)
      } else {
        stored_token = token
        update({ needs_install: true })
      }
    } catch (e) {
      if (gen !== generation) return
      update({
        oauth_error: e instanceof Error ? e.message : "Failed to verify access",
      })
    } finally {
      if (gen === generation) {
        update({ checking_access: false })
      }
    }
  }

  function start() {
    const popup = window.open("about:blank", "_blank")

    if (cancel_oauth) {
      cancel_oauth()
    }

    stored_token = null
    generation++
    const this_generation = generation

    state.set({
      ...INITIAL_STATE,
      oauth_starting: true,
    })

    const callbacks: OAuthFlowCallbacks = {
      onStarted: (response) => {
        if (this_generation !== generation) return
        update({
          install_url: response.install_url,
          authorize_url: response.authorize_url,
          popup_blocked: response.popup_blocked,
          oauth_starting: false,
        })
      },
      onPolling: () => {
        if (this_generation !== generation) return
      },
      onSuccess: (token: string) => {
        if (this_generation !== generation) return
        check_access(token, this_generation)
      },
      onError: (err: string) => {
        if (this_generation !== generation) return
        update({ oauth_starting: false, oauth_error: err })
      },
    }

    const handle = startOAuthFlow(options.git_url, callbacks, popup)
    cancel_oauth = handle.cancel
  }

  function open_install() {
    const current_install_url = get(state).install_url
    if (!current_install_url) return
    const popup = window.open(current_install_url, "_blank")
    if (!popup) {
      update({ popup_blocked: true })
      return
    }
    update({ install_clicked: true, popup_blocked: false })
  }

  async function verify_access() {
    if (!stored_token) return
    update({ oauth_error: null })
    generation++
    await check_access(stored_token, generation)
  }

  function destroy() {
    if (cancel_oauth) {
      cancel_oauth()
      cancel_oauth = null
    }
  }

  return {
    state,
    start,
    reset,
    open_install,
    verify_access,
    destroy,
  }
}
