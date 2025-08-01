<script lang="ts">
  import ConnectProviders from "./connect_providers.svelte"

  let has_connected_providers = false
  let intermediate_step = false
  let next_visible = false
  let centered = true
  $: next_visible = !intermediate_step && has_connected_providers
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Connect AI Providers
</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  Kiln is free, but your need to connect API keys to use AI services.
</h3>

<div
  class="flex-none min-h-[50vh] py-8 px-4 h-full flex flex-col py-18 w-full mx-auto"
>
  <ConnectProviders
    bind:has_connected_providers
    bind:intermediate_step
    bind:centered
  />
</div>

<div
  class="flex-none flex flex-col place-content-center md:flex-row gap-4 pt-4"
>
  <a
    href="/setup/create_project"
    class="flex-none {next_visible ? '' : 'hidden'}"
  >
    <button class="btn btn-primary w-full min-w-[130px]"> Continue </button>
  </a>
</div>
