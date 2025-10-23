<script lang="ts">
  import SettingsHeader from "./settings_header.svelte"
  import SettingsItem from "./settings_item.svelte"
  import type { SettingsSectionItem } from "./settings_section_types"

  export let title: string
  export let items: Array<SettingsSectionItem>
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
        <SettingsItem
          name={item.highlight_title || item.name}
          description={item.description}
          button_text="Create"
          on_click={item.on_select}
          badge_text={item.recommended ? "Recommended" : undefined}
        />
      {/if}
    {/each}
  </div>
</div>
