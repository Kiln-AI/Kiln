<script lang="ts">
  import SidebarRailTooltip from "./sidebar_rail_tooltip.svelte"

  export let href: string
  export let active: boolean = false
  export let label: string

  let hovered = false
  let focused = false
  $: show_tooltip = hovered || focused
</script>

<div class="flex justify-center">
  <a
    {href}
    class="relative flex items-center justify-center w-10 h-8 xl:h-9 rounded-md {active
      ? 'bg-base-300'
      : 'hover:bg-base-300/50'}"
    aria-label={label}
    aria-current={active ? "page" : undefined}
    on:mouseenter={() => (hovered = true)}
    on:mouseleave={() => (hovered = false)}
    on:focus={() => (focused = true)}
    on:blur={() => (focused = false)}
  >
    <span class="w-5 h-5 block">
      <slot name="icon" />
    </span>
    <SidebarRailTooltip show={show_tooltip}>{label}</SidebarRailTooltip>
  </a>
</div>
