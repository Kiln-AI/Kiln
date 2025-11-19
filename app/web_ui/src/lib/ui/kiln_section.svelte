<script lang="ts">
  import SettingsHeader from "./settings_header.svelte"
  import SettingsItem from "./settings_item.svelte"
  import type { KilnSectionItem, SpecTemplateItem } from "./kiln_section_types"

  export let title: string
  export let items: Array<KilnSectionItem>
  // Carousel is only supported for spec_template items. Other item types will fall back to default SettingsItem rendering.
  export let use_carousel_for_spec_templates: boolean = false

  $: spec_template_items = use_carousel_for_spec_templates
    ? items.filter(
        (item): item is SpecTemplateItem => item.type === "spec_template",
      )
    : []
  $: other_items = use_carousel_for_spec_templates
    ? items.filter((item) => item.type !== "spec_template")
    : items
</script>

<div class="space-y-6">
  <SettingsHeader {title} />

  {#if use_carousel_for_spec_templates && spec_template_items.length > 0}
    <div
      class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 auto-rows-fr gap-4 max-w-7xl"
    >
      {#each spec_template_items as item}
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

  <div class="space-y-1">
    {#each other_items as item}
      {#if item.type === "settings"}
        <SettingsItem
          name={item.name}
          badge_text={item.badge_text}
          description={item.description}
          button_text={item.button_text}
          href={item.href}
          on_click={item.on_click}
          is_external={item.is_external || false}
        />
      {:else if item.type === "eval_template"}
        <SettingsItem
          name={item.highlight_title || item.name}
          description={item.description}
          button_text="Create"
          on_click={item.on_select}
          badge_text={item.recommended ? "Recommended" : undefined}
        />
      {:else if item.type === "spec_template"}
        <SettingsItem
          name={item.name}
          description={item.description}
          button_text="Create"
          on_click={item.on_select}
        />
      {/if}
    {/each}
  </div>
</div>
