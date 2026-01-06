<script lang="ts">
  import CheckmarkIcon from "$lib/ui/icons/checkmark_icon.svelte"

  export let title: string
  export let description: string
  export let features: string[] = []
  export let badge: string | null = null
  export let highlighted: boolean = false
  export let checkmarkColor: "default" | "primary" = "default"

  $: checkmarkClass = checkmarkColor === "primary" ? "text-primary" : ""
</script>

<div
  class="card card-bordered border-base-300 shadow-md p-6 flex flex-col {highlighted
    ? 'bg-base-200'
    : ''}"
>
  <div class="flex-1">
    <div class="flex items-center gap-2 mb-2">
      <h4 class="text-lg font-medium">{title}</h4>
      {#if badge}
        <span class="badge badge-primary badge-sm">{badge}</span>
      {/if}
    </div>
    <p class="text-sm text-gray-500 mb-4">
      {description}
    </p>

    <slot name="content" />

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

  <div class="mt-6">
    <slot name="actions" />
  </div>
</div>
