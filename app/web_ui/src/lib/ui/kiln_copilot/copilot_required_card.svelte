<script lang="ts">
  import { goto } from "$app/navigation"
  import type { KilnError } from "$lib/utils/error_handlers"

  export let description: string
  export let auth_url: string
  export let back_url: string | null = null
  export let back_label: string
  export let error: KilnError | null = null
</script>

<div class="max-w-[600px] mx-auto">
  <div class="p-8 text-center">
    <div class="flex justify-center mb-4">
      <img src="/images/animated_logo.svg" alt="Kiln Copilot" class="size-16" />
    </div>
    <h2 class="text-2xl font-bold mb-3">Kiln Copilot Required</h2>
    <p class="text-gray-600 mb-6">{description}</p>
    {#if error}
      <div class="bg-error/10 border border-error/20 rounded-lg p-3 mb-6">
        <div class="text-error text-sm">
          {error.getMessage() || "Failed to check Kiln Copilot connection"}
        </div>
      </div>
    {/if}
    <div class="flex flex-col gap-3">
      <button class="btn btn-primary" on:click={() => goto(auth_url)}>
        Connect Kiln Copilot
      </button>
      {#if back_url}
        <a href={back_url} class="link text-sm text-gray-600">
          {back_label}
        </a>
      {/if}
    </div>
  </div>
</div>
