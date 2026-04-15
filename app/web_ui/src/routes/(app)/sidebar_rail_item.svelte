<script lang="ts">
  import Float from "$lib/ui/float.svelte"

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
    class="relative flex items-center justify-center w-10 h-9 rounded-md {active
      ? 'bg-base-300'
      : 'hover:bg-base-300/50'}"
    data-tip={label}
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
    {#if show_tooltip}
      <Float placement="right" offset_px={8} role="tooltip">
        <span
          class="pointer-events-none px-2 py-1 rounded bg-neutral text-neutral-content text-xs whitespace-nowrap shadow-md"
        >
          {label}
        </span>
      </Float>
    {/if}
  </a>
</div>
