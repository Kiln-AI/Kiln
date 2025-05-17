<script lang="ts">
  export let options: {
    id: string
    name: string
    description: string
    recommended?: boolean
    highlight_title?: string
  }[]

  export let select_option: (id: string) => void
</script>

<div class="flex flex-col gap-6 pt-4 max-w-[500px]">
  {#each options as option}
    <button
      class="cursor-pointer text-left"
      on:click={() => {
        select_option(option.id)
      }}
    >
      <div
        class="card card-bordered border-base-300 bg-base-200 shadow-md w-full p-6 indicator"
      >
        {#if option.recommended}
          <div class="indicator-item indicator-center badge badge-primary">
            Recommended
          </div>
        {:else if option.highlight_title}
          <div class="indicator-item indicator-center badge badge-secondary">
            {option.highlight_title}
          </div>
        {/if}
        <div class="flex flex-col">
          <div class="font-medium">
            {option.name}
          </div>
          <div class="font-light pt-1">
            {option.description}
          </div>
        </div>
      </div>
    </button>
  {/each}
</div>
