<script lang="ts">
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import ConnectKilnCopilotSteps from "./connect_kiln_copilot_steps.svelte"
  import AppPage from "../../../routes/(app)/app_page.svelte"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"

  export let title: string
  export let docs_link: string
  export let breadcrumbs: Array<{ label: string; href: string }>
  export let success_redirect_url: string

  let connect_success = false
  // Until the already-connected check resolves, render a spinner instead of
  // the connect card — otherwise users who are already connected briefly
  // flash the "Connect Kiln Pro" screen before the redirect fires.
  let checking = true

  function proceed() {
    goto(success_redirect_url)
  }

  onMount(async () => {
    // A fresh OAuth callback (?code=...) must be handled by
    // ConnectKilnCopilotSteps — don't short-circuit it.
    const params = new URLSearchParams(window.location.search)
    if (params.has("code")) {
      checking = false
      return
    }
    try {
      if (await checkKilnCopilotAvailable()) {
        // Already connected — skip the connect screen entirely.
        goto(success_redirect_url, { replaceState: true })
        return
      }
    } catch {
      // Settings check failed — fall through and show the connect screen.
    }
    checking = false
  })
</script>

<AppPage
  {title}
  sub_subtitle="Read the Docs"
  sub_subtitle_link={docs_link}
  {breadcrumbs}
>
  {#if checking}
    <div class="flex justify-center my-24 md:my-36">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>
  {:else}
    <div
      class="flex flex-col max-w-[400px] mx-auto mt-24 md:mt-36 border border-base-300 rounded-2xl bg-base-100 px-6 shadow-lg py-8 md:py-12"
    >
      <ConnectKilnCopilotSteps
        onSuccess={() => (connect_success = true)}
        showCheckmark={connect_success}
      />
      {#if connect_success}
        <button
          class="btn btn-primary mt-4 btn-wide mx-auto"
          on:click={proceed}
        >
          Continue
        </button>
      {/if}
    </div>
  {/if}
</AppPage>
