<script lang="ts">
  import SettingsHeader from "./settings_header.svelte"
  import SettingsItem from "./settings_item.svelte"

  export let title: string
  export let items: Array<{
    name: string
    description: string
    button_text: string
    href?: string
    on_click?: () => void
    is_external?: boolean
    badge_text?: string
  }>
</script>

<div class="space-y-6">
  <SettingsHeader {title} />

  <div class="space-y-1">
    {#each items as item}
      <SettingsItem
        name={item.name}
        badge_text={item.badge_text}
        description={item.description}
        button_text={item.button_text}
        href={item.href}
        on_click={item.on_click}
        is_external={item.is_external || false}
      />
    {/each}
  </div>
</div>
