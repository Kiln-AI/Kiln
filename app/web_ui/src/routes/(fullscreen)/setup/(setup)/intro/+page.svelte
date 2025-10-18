<script lang="ts">
  import Tutorial from "./tutorial.svelte"

  let completed: boolean = false
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Introduction
</h1>

<div
  class="flex-none min-h-[50vh] mt-8 lg:mt-16 px-4 h-full flex flex-col py-18 w-full mx-auto"
>
  <Tutorial bind:completed />
</div>

<div class="flex-none flex flex-col place-content-center md:flex-row gap-4">
  {#if completed}
    <a href="/setup/select_account">
      <button class="btn btn-primary w-full min-w-[130px]"> Continue </button>
    </a>
  {:else}
    <a class="btn" href="/setup/select_account"> Skip Tutorial </a>
  {/if}
</div>
