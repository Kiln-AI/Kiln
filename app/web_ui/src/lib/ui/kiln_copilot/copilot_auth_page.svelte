<script lang="ts">
  import { goto } from "$app/navigation"
  import ConnectKilnCopilotSteps from "./connect_kiln_copilot_steps.svelte"
  import AppPage from "../../../routes/(app)/app_page.svelte"

  export let title: string
  export let docs_link: string
  export let breadcrumbs: Array<{ label: string; href: string }>
  export let success_redirect_url: string

  let connect_success = false

  function proceed() {
    goto(success_redirect_url)
  }
</script>

<AppPage
  {title}
  sub_subtitle="Read the Docs"
  sub_subtitle_link={docs_link}
  {breadcrumbs}
>
  <div
    class="flex flex-col max-w-[400px] mx-auto mt-24 md:mt-36 border border-base-300 rounded-2xl bg-base-100 px-6 shadow-lg py-8 md:py-12"
  >
    <ConnectKilnCopilotSteps
      onSuccess={() => (connect_success = true)}
      showCheckmark={connect_success}
    />
    {#if connect_success}
      <button class="btn btn-primary mt-4 btn-wide mx-auto" on:click={proceed}>
        Continue
      </button>
    {/if}
  </div>
</AppPage>
