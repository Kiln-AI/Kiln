<script lang="ts">
  import type { OptionListItem } from "./option_list_types"

  export let options: OptionListItem[]
  export let select_option: (id: string) => void
</script>

<div class="flex flex-col gap-3">
  {#each options as option}
    <button
      type="button"
      class="card card-bordered border-base-300 bg-base-100 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 w-full text-left p-4 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-md disabled:hover:border-base-300 disabled:hover:shadow-md"
      on:click={() => select_option(option.id)}
      disabled={option.disabled}
    >
      <div class="flex items-center gap-4 w-full">
        {#if option.icon}
          <div
            class="option-icon flex items-center justify-center rounded-[10px] flex-none w-11 h-11 p-[9px] bg-blue-50 text-[#628BD9]"
          >
            <svelte:component this={option.icon} />
          </div>
        {/if}
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-medium">{option.name}</span>
            {#if option.recommended}
              <span class="badge badge-sm badge-primary whitespace-nowrap"
                >&#9733; Recommended</span
              >
            {/if}
            {#each option.tags ?? [] as tag}
              <span
                class="badge badge-sm badge-outline whitespace-nowrap {tag.tone ===
                'beta'
                  ? 'badge-primary'
                  : ''}">{tag.label}</span
              >
            {/each}
          </div>
          <div class="text-sm text-gray-500 mt-0.5">
            {option.description}
          </div>
        </div>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="currentColor"
          class="flex-none ml-auto text-gray-500"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"
          />
        </svg>
      </div>
    </button>
  {/each}
</div>

<style>
  .option-icon :global(svg) {
    width: 100%;
    height: 100%;
    display: block;
  }
</style>
