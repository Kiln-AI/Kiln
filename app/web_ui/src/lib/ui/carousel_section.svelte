<script lang="ts">
  import SettingsHeader from "./settings_header.svelte"
  import type { CarouselSectionItem } from "./kiln_section_types"

  export let title: string
  export let items: Array<CarouselSectionItem>
</script>

<div class="space-y-6">
  <SettingsHeader {title} />
  {#if items.length > 0}
    <div
      class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 auto-rows-fr gap-4 max-w-7xl"
    >
      {#each items as item}
        <div
          class="card card-bordered border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 transform hover:-translate-y-1 hover:z-10 h-full flex flex-col"
          on:click={item.on_select}
          on:keydown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              item.on_select()
            }
          }}
          tabindex="0"
          role="button"
          aria-label="Create {item.name}"
        >
          <div class="card-body p-4 flex flex-col flex-1">
            <h3 class="card-title text-lg font-semibold leading-tight">
              {item.name}
            </h3>
            <p class="text-base-content/70 text-xs leading-relaxed mt-1 flex-1">
              {item.description}
            </p>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
