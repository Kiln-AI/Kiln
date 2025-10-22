<script lang="ts">
  import SettingsHeader from "./settings_header.svelte"
  import SettingsItem from "./settings_item.svelte"
  import EvalTemplateItem from "./eval_template_item.svelte"
  import type { KilnSectionItem } from "./kiln_section_types"

  export let title: string
  export let items: Array<KilnSectionItem>
</script>

<div class="space-y-6">
  <SettingsHeader {title} />

  <div class="space-y-1">
    {#each items as item}
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
        <EvalTemplateItem
          name={item.name}
          description={item.description}
          recommended={item.recommended || false}
          highlight_title={item.highlight_title}
          on_select={item.on_select}
        />
      {/if}
    {/each}
  </div>
</div>
