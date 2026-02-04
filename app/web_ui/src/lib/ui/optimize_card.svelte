<script lang="ts">
  export let title: string
  export let description: string
  export let cost: number
  export let effort: number
  export let onClick: () => void

  const metrics = [
    { label: "Cost", value: cost },
    { label: "Effort", value: effort },
  ]

  function handleKeyPress(event: KeyboardEvent) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      onClick()
    }
  }
</script>

<div
  class="card card-bordered border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 transform hover:-translate-y-1 hover:z-10 h-full flex flex-col p-4"
  on:click={onClick}
  on:keydown={handleKeyPress}
  role="button"
  tabindex="0"
  aria-label={title}
>
  <div class="p-0">
    <div class="text-lg font-semibold leading-tight line-clamp-1">{title}</div>
    <div class="text-xs text-gray-500 font-medium mt-2 mb-4">
      {description}
    </div>

    <div class="flex-1 flex items-center">
      <div class="space-y-4 w-full">
        {#each metrics as metric}
          <div class="flex items-center gap-4">
            <span class="text-gray-500 w-12 text-xs">{metric.label}</span>
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
  </div>
</div>
