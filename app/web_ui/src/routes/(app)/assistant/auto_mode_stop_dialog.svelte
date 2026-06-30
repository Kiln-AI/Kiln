<script lang="ts">
  import posthog from "posthog-js"
  import Dialog from "$lib/ui/dialog.svelte"

  let dialog: Dialog

  let pendingResolve: ((confirmed: boolean) => void) | null = null
  let pendingPromise: Promise<boolean> | null = null

  /**
   * Open the Stop confirmation gate. Resolves ``true`` when the user confirms
   * the hard stop, ``false`` on cancel / dismiss / Escape / backdrop.
   *
   * The point of the dialog is to set expectations: stopping halts the agent
   * immediately, but any background jobs it already kicked off (evals,
   * optimization runs) are independent and keep running — Stop does not cancel
   * them.
   */
  export function prompt(): Promise<boolean> {
    if (pendingPromise) return pendingPromise
    posthog.capture("chat_auto_mode_stop_shown")
    pendingPromise = new Promise<boolean>((resolve) => {
      pendingResolve = resolve
      dialog.show()
    })
    return pendingPromise
  }

  function settle(confirmed: boolean) {
    const resolve = pendingResolve
    pendingResolve = null
    pendingPromise = null
    resolve?.(confirmed)
  }

  function confirm(): boolean {
    posthog.capture("chat_auto_mode_stop_confirmed")
    settle(true)
    return true // close dialog
  }

  function dismiss() {
    if (pendingResolve === null) return
    posthog.capture("chat_auto_mode_stop_cancelled")
    settle(false)
  }
</script>

<Dialog
  bind:this={dialog}
  title="Stop the agent?"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Stop agent", isError: true, action: confirm },
  ]}
  on:cancel={() => dismiss()}
  on:close={() => dismiss()}
>
  <div class="text-sm">
    <p class="leading-relaxed">
      The agent won't start anything new, but any jobs it already kicked off
      (like evals) keep running in the background.
    </p>
  </div>
</Dialog>
