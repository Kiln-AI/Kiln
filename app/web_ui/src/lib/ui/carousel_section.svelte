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
        {@const disabled = "disabled" in item && item.disabled ? true : false}
        {@const disabled_reason =
          "disabled_reason" in item ? item.disabled_reason : undefined}
        <div
          class="card card-bordered border-base-300 shadow-md h-full flex flex-col {disabled
            ? 'opacity-50 cursor-not-allowed'
            : 'hover:shadow-lg hover:border-primary/50 transition-all duration-200 transform hover:-translate-y-1 hover:z-10 cursor-pointer'}"
          on:click={() => {
            if (!disabled) item.on_select()
          }}
          on:keydown={(e) => {
            if (!disabled && (e.key === "Enter" || e.key === " ")) {
              e.preventDefault()
              item.on_select()
            }
          }}
          tabindex={disabled ? -1 : 0}
          role="button"
          aria-label="Create {item.name}"
          aria-disabled={disabled}
        >
          <div class="p-4">
            <h3 class="card-title text-lg font-semibold leading-tight">
              {item.name}
            </h3>
            <p
              class="text-gray-500 text-xs font-medium leading-relaxed mt-1 flex-1"
            >
              {item.description}
            </p>
            {#if disabled && disabled_reason}
              <p class="text-warning text-xs mt-2">
                {disabled_reason}
              </p>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
