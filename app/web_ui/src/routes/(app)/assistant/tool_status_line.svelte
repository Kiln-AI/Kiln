<script lang="ts">
  import Float from "$lib/ui/float.svelte"
  import BrailleSpinner from "./braille_spinner.svelte"

  export let variant: "fetched" | "saved" | "fetching" | "saving"
  export let detail: string = ""
  export let mutedClass: string = "text-base-content/50"

  let truncEl: HTMLDivElement | null = null
  let hovering = false
  let overflowing = false

  const LABELS = {
    fetched: "Fetched data",
    saved: "Saved data",
    fetching: "Fetching data",
    saving: "Saving data",
  } as const

  $: label = LABELS[variant]
  $: isLoading = variant === "fetching" || variant === "saving"
  $: fullText = detail ? `${label} ${detail}` : label

  function measureOverflow() {
    if (!truncEl) {
      overflowing = false
      return
    }
    overflowing = truncEl.scrollWidth - truncEl.clientWidth > 0.5
  }

  function onEnter() {
    measureOverflow()
    hovering = true
  }

  function onLeave() {
    hovering = false
  }
</script>

<div
  class="flex items-center gap-1.5 text-sm text-base-content/50 py-0.5 min-w-0"
  role="presentation"
  on:mouseenter={onEnter}
  on:mouseleave={onLeave}
  on:focusin={onEnter}
  on:focusout={onLeave}
>
  {#if isLoading}
    <BrailleSpinner />
  {:else}
    <span class="inline-block w-3 text-center shrink-0">✓</span>
  {/if}
  <div bind:this={truncEl} class="truncate min-w-0 flex-1">
    {label}{#if isLoading}<span class="inline-flex items-baseline gap-px"
        ><span class="thinking-dot" style="animation-delay: 0ms">.</span><span
          class="thinking-dot"
          style="animation-delay: 160ms">.</span
        ><span class="thinking-dot" style="animation-delay: 320ms">.</span
        ></span
      >{/if}{#if detail}<span class="text-base-content/35 ml-1">{detail}</span
      >{/if}
  </div>
  {#if hovering && overflowing}
    <Float
      portal={true}
      placement="top"
      role="tooltip"
      offset_px={6}
      shift_padding={8}
    >
      <div
        class="pointer-events-none px-3 py-2 text-xs bg-neutral text-neutral-content rounded shadow-lg max-w-sm whitespace-normal break-words leading-snug"
      >
        {fullText}
      </div>
    </Float>
  {/if}
</div>
