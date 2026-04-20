<script lang="ts">
  import Warning from "$lib/ui/warning.svelte"
  import type { OAuthWithInstallState } from "$lib/git_sync/oauth_with_install"
  import PopupBlockedFallback from "$lib/git_sync/popup_blocked_fallback.svelte"

  export let state: OAuthWithInstallState
  export let open_install: () => void
  export let verify_access: () => Promise<void>
  export let reset: () => void
  export let compact: boolean = false
</script>

<div class="flex flex-col items-center py-4 {compact ? 'gap-3' : 'gap-4'}">
  <div
    class="{compact
      ? 'w-10 h-10'
      : 'w-12 h-12'} rounded-full bg-success/10 flex items-center justify-center"
  >
    <svg
      class="{compact ? 'w-5 h-5' : 'w-6 h-6'} text-success"
      fill="none"
      viewBox="0 0 24 24"
      stroke-width="2"
      stroke="currentColor"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M4.5 12.75l6 6 9-13.5"
      />
    </svg>
  </div>
  <p class="{compact ? 'text-xs' : 'text-sm'} font-medium">
    {compact ? "Authorized" : "Step 1: Authorized"}
  </p>

  <div
    class="w-full border-t border-base-200 {compact ? 'my-1' : 'my-2'}"
  ></div>

  <p class="text-sm font-medium">
    {compact
      ? "Install App on Repository"
      : "Step 2: Install App on Repository"}
  </p>
  <p
    class="{compact ? 'text-xs' : 'text-sm'} text-gray-500 text-center {compact
      ? ''
      : 'max-w-sm'}"
  >
    {compact
      ? "Install the Kiln Sync GitHub App on the repository, then verify access."
      : "The Kiln Sync GitHub App needs to be installed on the repository to enable syncing. Click below to install it, then come back and verify."}
  </p>
  {#if state.popup_blocked && state.install_url}
    <div class="w-full {compact ? '' : 'max-w-sm'}">
      <PopupBlockedFallback
        url={state.install_url}
        message="Your browser blocked the popup. Copy the link below and open it manually in a new tab to install the app."
        {compact}
      />
    </div>
  {:else}
    <button
      class="btn w-full {compact ? '' : 'max-w-sm'} {state.install_clicked
        ? compact
          ? 'btn-xs btn-ghost'
          : 'btn-sm btn-ghost'
        : compact
          ? 'btn-primary btn-sm'
          : 'btn-primary'}"
      on:click={open_install}
    >
      {state.install_clicked
        ? "Retry Install on GitHub"
        : "Install Kiln Sync on GitHub"}
    </button>
  {/if}
  <button
    class="btn w-full {compact ? '' : 'max-w-sm'} {state.install_clicked ||
    state.popup_blocked
      ? compact
        ? 'btn-primary btn-sm'
        : 'btn-primary'
      : compact
        ? 'btn-xs btn-ghost'
        : 'btn-sm btn-ghost'}"
    on:click={verify_access}
    disabled={state.checking_access}
  >
    {#if state.checking_access}
      <span class="loading loading-spinner loading-xs"></span>
    {/if}
    Verify Access
  </button>
  {#if state.oauth_error}
    <div class="w-full {compact ? '' : 'max-w-sm'}">
      <Warning warning_message={state.oauth_error} warning_color="error" />
    </div>
  {/if}
  <button
    class="btn btn-link btn-xs text-gray-500 no-underline hover:text-gray-700 hover:underline focus-visible:underline"
    on:click={reset}
  >
    Start over
  </button>
</div>
