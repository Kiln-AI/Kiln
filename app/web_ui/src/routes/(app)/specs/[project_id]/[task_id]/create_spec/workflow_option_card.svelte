<script lang="ts">
  import CheckmarkIcon from "$lib/ui/icons/checkmark_icon.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"

  export let title: string
  export let description: string
  export let features: string[] = []
  export let badge: string | null = null
  export let highlighted: boolean = false
  export let checkmarkColor: "default" | "primary" = "default"
  export let error: KilnError | null = null
  export let button_label: string
  export let button_primary: boolean = false
  export let on_click: () => void

  $: checkmarkClass = checkmarkColor === "primary" ? "text-primary" : ""
</script>

<div
  class="card card-bordered border-base-300 shadow-md p-6 flex flex-col {highlighted
    ? 'bg-base-200'
    : ''}"
>
  <div class="flex-1 mb-6">
    <div class="flex items-center gap-2 mb-2">
      <h4 class="text-lg font-medium">{title}</h4>
      {#if badge}
        <span class="badge badge-primary badge-sm">{badge}</span>
      {/if}
    </div>
    <p class="text-sm text-gray-500 mb-4">
      {description}
    </p>

    {#if features.length > 0}
      <ul class="text-sm text-gray-500 space-y-2">
        {#each features as feature}
          <li class="flex items-start gap-2">
            <div class="w-4 h-4 mt-0.5 shrink-0 {checkmarkClass}">
              <CheckmarkIcon />
            </div>
            <span>{feature}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  {#if error}
    <div class="text-center text-sm text-error mb-2">
      {#each error.getErrorMessages() as error_line}
        <div>{error_line}</div>
      {/each}
    </div>
  {/if}

  <button
    class="btn w-full {button_primary ? 'btn-primary' : 'btn-outline'}"
    on:click={on_click}
  >
    {button_label}
  </button>
</div>
