<script lang="ts">
  import SettingsHeader from "./settings_header.svelte"
  import Dialog from "./dialog.svelte"
  import type { CarouselSectionItem } from "./kiln_section_types"

  export let title: string
  export let items: Array<CarouselSectionItem>
  export let min_width: number | null = null
  export let min_height: number | null = null

  let disabled_dialog: Dialog
  let disabled_dialog_reason: string = ""
  let disabled_dialog_docs_link: string | undefined = undefined

  function handle_click(item: CarouselSectionItem) {
    const disabled = "disabled" in item && item.disabled
    if (disabled) {
      disabled_dialog_reason =
        "disabled_reason" in item && item.disabled_reason
          ? item.disabled_reason
          : "This option is not available."
      disabled_dialog_docs_link =
        "disabled_docs_link" in item ? item.disabled_docs_link : undefined
      disabled_dialog.show()
    } else {
      item.on_select()
    }
  }
</script>

<Dialog title="Option Unavailable" bind:this={disabled_dialog}>
  <p class="text-sm">
    {disabled_dialog_reason}
  </p>
  {#if disabled_dialog_docs_link}
    <div class="flex justify-end mt-6">
      <a
        href={disabled_dialog_docs_link}
        target="_blank"
        rel="noopener noreferrer"
        class="link text-sm text-gray-500"
      >
        Learn More
      </a>
    </div>
  {/if}
</Dialog>

<div class="space-y-6">
  <SettingsHeader {title} />
  {#if items.length > 0}
    <div
      class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 auto-rows-fr gap-4 max-w-7xl"
      style={min_width
        ? `grid-template-columns: repeat(auto-fill, minmax(${min_width}px, 1fr))`
        : ""}
    >
      {#each items as item}
        {@const recommended =
          "recommended" in item && item.recommended ? true : false}
        <div
          class="card card-bordered border-base-300 shadow-md h-full flex flex-col hover:shadow-lg hover:border-primary/50 transition-all duration-200 transform hover:-translate-y-1 hover:z-10 cursor-pointer"
          style={min_height ? `min-height: ${min_height}px` : ""}
          on:click={() => handle_click(item)}
          on:keydown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              handle_click(item)
            }
          }}
          tabindex={0}
          role="button"
          aria-label="Create {item.name}"
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
            {#if recommended}
              <div class="flex justify-end mt-2">
                <div class="badge badge-sm badge-primary">Recommended</div>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
