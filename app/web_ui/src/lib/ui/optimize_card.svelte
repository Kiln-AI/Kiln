<script lang="ts">
  import InfoTooltip from "./info_tooltip.svelte"

  export let title: string
  export let description: string
  export let info_description: string | undefined = undefined
  export let cost: number
  export let complexity: number
  export let speed: number
  export let onClick: () => void

  const metrics = [
    { label: "Cost", value: cost },
    { label: "Complexity", value: complexity },
    { label: "Speed", value: speed },
  ]

  function handleKeyPress(event: KeyboardEvent) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      onClick()
    }
  }
</script>

<div
  class="card card-bordered max-w-96 w-full border-base-300 shadow-md p-6 cursor-pointer hover:shadow-lg hover:border-primary/50 transition-all duration-200"
  on:click={onClick}
  on:keypress={handleKeyPress}
  role="button"
  tabindex="0"
>
  <div class="flex flex-row items-center justify-between mb-2">
    <h3 class="text-xl font-medium line-clamp-1">{title}</h3>
    {#if info_description}
      <InfoTooltip tooltip_text={info_description} />
    {/if}
  </div>
  <p class="text-gray-500 mb-4 text-sm">
    {description}
  </p>

  <div class="space-y-4">
    {#each metrics as metric}
      <div class="flex items-center gap-4">
        <span class="text-gray-500 w-24 text-sm">{metric.label}</span>
        <div class="flex gap-2 flex-1">
          {#each Array(5) as _, i}
            <div
              class="h-3 rounded-full flex-1 {i < metric.value
                ? 'bg-secondary'
                : 'bg-gray-200'}"
            />
          {/each}
        </div>
      </div>
    {/each}
  </div>
</div>
