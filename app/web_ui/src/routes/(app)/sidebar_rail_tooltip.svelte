<script lang="ts">
  import Float from "$lib/ui/float.svelte"

  export let show: boolean = false
  export let offset_px: number = 8
  // "single" = one-line nav label (default); "multi" = multi-line block
  // content (e.g. task chip with task name + project name).
  export let variant: "single" | "multi" = "single"
  // Most rail tooltips duplicate the anchor's aria-label (purely visual), so
  // default to no role and aria-hidden to avoid double-announcing. Callers
  // with meaningful tooltip content (e.g. the task chip's project name) can
  // override by passing role="tooltip" and aria_hidden={false}.
  export let role: "none" | "tooltip" = "none"
  export let aria_hidden: boolean = true
  // Stable id used by consumers to wire `aria-describedby` on the trigger
  // when the tooltip carries semantic content not already in aria-label.
  export let id: string | undefined = undefined
</script>

{#if show}
  <Float placement="right" {offset_px} {role} portal>
    {#if variant === "multi"}
      <span
        {id}
        data-testid="rail-tooltip"
        class="pointer-events-none px-3 py-1.5 rounded bg-neutral text-neutral-content text-xs flex flex-col items-start text-left shadow-md gap-[1px] leading-tight"
        aria-hidden={aria_hidden ? "true" : undefined}
      >
        <slot />
      </span>
    {:else}
      <span
        {id}
        data-testid="rail-tooltip"
        class="pointer-events-none px-2 py-1 rounded bg-neutral text-neutral-content text-sm font-medium whitespace-nowrap shadow-md"
        aria-hidden={aria_hidden ? "true" : undefined}
      >
        <slot />
      </span>
    {/if}
  </Float>
{/if}
