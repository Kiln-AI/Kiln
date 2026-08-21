<script lang="ts">
  import posthog from "posthog-js"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { AutoModeConsentRequiredPayload } from "$lib/chat/streaming_chat"

  let dialog: Dialog

  let reason: string | null = null
  let pendingResolve: ((accepted: boolean) => void) | null = null
  let pendingPromise: Promise<boolean> | null = null

  /**
   * Open the consent gate. Resolves ``true`` if the user turns on auto mode,
   * ``false`` on cancel / dismiss / Escape / backdrop. Consent is required every
   * time (functional spec §4.2) — this never auto-accepts.
   *
   * ``payload`` is optional: the backend-tool path passes the model's reason;
   * the manual footer toggle opens it with no payload.
   */
  export function prompt(
    payload?: AutoModeConsentRequiredPayload | null,
  ): Promise<boolean> {
    if (pendingPromise) return pendingPromise
    reason = payload?.reason ?? null
    posthog.capture("chat_auto_mode_consent_shown", {
      has_reason: !!reason,
      triggered_by_model: !!payload,
    })
    pendingPromise = new Promise<boolean>((resolve) => {
      pendingResolve = resolve
      dialog.show()
    })
    return pendingPromise
  }

  function settle(accepted: boolean) {
    const resolve = pendingResolve
    pendingResolve = null
    pendingPromise = null
    resolve?.(accepted)
  }

  function accept(): boolean {
    posthog.capture("chat_auto_mode_consent_accepted")
    settle(true)
    return true // close dialog
  }

  function dismiss() {
    if (pendingResolve === null) return
    posthog.capture("chat_auto_mode_consent_declined")
    settle(false)
  }
</script>

<Dialog
  bind:this={dialog}
  title="Turn on auto mode?"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Turn on auto mode", isPrimary: true, action: accept },
  ]}
  on:cancel={() => dismiss()}
  on:close={() => dismiss()}
>
  <div class="flex flex-col gap-3 text-sm">
    {#if reason}
      <div
        class="rounded-lg border-l-4 border-primary/60 bg-base-200/60 px-3 py-2 text-base-content/80 italic"
      >
        The assistant suggests auto mode to: {reason}
      </div>
    {/if}

    <p class="leading-relaxed">
      Auto mode lets the assistant <span class="font-semibold"
        >run steps on its own</span
      > to make progress without stopping to ask you each time.
    </p>

    <div>
      <p class="text-base-content/70 mb-1.5">While it's on:</p>
      <ul class="flex flex-col gap-1.5 pl-1">
        <li class="flex items-start gap-2">
          <span class="text-base-content/40 shrink-0 mt-0.5">•</span>
          <span>
            It will <span class="font-semibold"
              >run tool calls and Kiln API actions without asking for approval</span
            > — including actions you'd normally confirm.
          </span>
        </li>
        <li class="flex items-start gap-2">
          <span class="text-base-content/40 shrink-0 mt-0.5">•</span>
          <span>
            It may <span class="font-semibold">start costly jobs</span> (for
            example, reflective optimization runs) that
            <span class="font-semibold">use tokens and can incur real cost</span
            >.
          </span>
        </li>
        <li class="flex items-start gap-2">
          <span class="text-base-content/40 shrink-0 mt-0.5">•</span>
          <span>
            It <span class="font-semibold"
              >keeps working on the server even if you close this window</span
            >, until it finishes, needs your input, or you stop it.
          </span>
        </li>
      </ul>
    </div>

    <p class="text-base-content/70 leading-relaxed">
      Auto mode stays on for this conversation. It pauses when the assistant
      needs your input or finishes a step, then resumes automatically on your
      next message — it keeps approving tool calls until you stop it (or the
      assistant turns it off).
    </p>
  </div>
</Dialog>
