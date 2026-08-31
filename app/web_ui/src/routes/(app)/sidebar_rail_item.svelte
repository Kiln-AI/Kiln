<script lang="ts">
  import SidebarRailTooltip from "./sidebar_rail_tooltip.svelte"

  // Either a navigation target (`href`) or a click handler (`on_click`). When
  // `on_click` is set the item renders as a button instead of a link (used by
  // the Jobs entry, which opens a dialog rather than navigating).
  export let href: string | undefined = undefined
  export let on_click: (() => void) | undefined = undefined
  export let active: boolean = false
  export let label: string

  let hovered = false
  let focused = false
  $: show_tooltip = hovered || focused

  $: item_class = `relative flex items-center justify-center w-10 h-8 xl:h-9 rounded-md ${
    active ? "bg-base-300" : "hover:bg-base-300/50"
  }`
</script>

<div class="flex justify-center">
  {#if on_click}
    <button
      type="button"
      class={item_class}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      on:click={on_click}
      on:mouseenter={() => (hovered = true)}
      on:mouseleave={() => (hovered = false)}
      on:focus={() => (focused = true)}
      on:blur={() => (focused = false)}
    >
      <span class="w-5 h-5 block">
        <slot name="icon" />
      </span>
      <SidebarRailTooltip show={show_tooltip}>{label}</SidebarRailTooltip>
    </button>
  {:else}
    <a
      {href}
      class={item_class}
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
  {/if}
</div>
