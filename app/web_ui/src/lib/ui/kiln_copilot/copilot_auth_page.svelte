<script lang="ts">
  import { goto } from "$app/navigation"
  import ConnectKilnCopilotSteps from "./connect_kiln_copilot_steps.svelte"
  import AppPage from "../../../routes/(app)/app_page.svelte"

  export let title: string
  export let docs_link: string
  export let breadcrumbs: Array<{ label: string; href: string }>
  export let success_redirect_url: string
  export let cancel_redirect_url: string

  let connect_success = false

  function proceed() {
    goto(success_redirect_url)
  }

  function cancel() {
    goto(cancel_redirect_url, { replaceState: true })
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    {title}
    sub_subtitle="Read the Docs"
    sub_subtitle_link={docs_link}
    {breadcrumbs}
  >
    <div class="flex flex-col max-w-[400px]">
      <ConnectKilnCopilotSteps
        onSuccess={() => (connect_success = true)}
        showCheckmark={connect_success}
      />
      {#if connect_success}
        <button class="btn btn-primary mt-4 w-full" on:click={proceed}>
          Next
        </button>
      {:else}
        <button class="link text-center text-sm mt-8" on:click={cancel}>
          Cancel setting up Kiln Copilot
        </button>
      {/if}
    </div>
  </AppPage>
</div>
