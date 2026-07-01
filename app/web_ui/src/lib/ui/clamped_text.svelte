<script lang="ts">
  import {
    onMount,
    onDestroy,
    afterUpdate,
    createEventDispatcher,
  } from "svelte"

  export let content: string = ""
  export let html_content: string | null = null
  export let max_lines: number = 4
  export let text_class: string = "whitespace-pre-wrap break-words"

  let container_el: HTMLElement | undefined
  let is_overflowing = false
  let resize_observer: ResizeObserver | null = null

  const dispatch = createEventDispatcher<{ see_all: void }>()

  // When overflowing, fade the text's own alpha toward the bottom. Using a
  // mask (rather than a background-colored gradient overlay) keeps this
  // background-agnostic, so it looks right on white or any tinted surface.
  const FADE =
    " -webkit-mask-image: linear-gradient(to bottom, black 60%, transparent); mask-image: linear-gradient(to bottom, black 60%, transparent);"
  $: fade_style = is_overflowing ? FADE : ""

  function check_overflow() {
    if (!container_el) return
    // 1px tolerance to avoid sub-pixel rounding flicker
    const overflowing =
      container_el.scrollHeight > container_el.clientHeight + 1
    if (overflowing !== is_overflowing) {
      is_overflowing = overflowing
    }
  }

  afterUpdate(check_overflow)

  onMount(() => {
    if (container_el) {
      resize_observer = new ResizeObserver(check_overflow)
      resize_observer.observe(container_el)
    }
  })

  onDestroy(() => {
    resize_observer?.disconnect()
  })
</script>

<div>
  {#if $$slots.default}
    <div
      bind:this={container_el}
      style="max-height: calc({max_lines} * 1.5em); overflow: hidden;{fade_style}"
    >
      <slot />
    </div>
  {:else}
    <!-- eslint-disable svelte/no-at-html-tags -->
    <pre
      bind:this={container_el}
      class={text_class}
      style="display: -webkit-box; -webkit-line-clamp: {max_lines}; -webkit-box-orient: vertical; overflow: hidden;{fade_style}">{#if html_content !== null}{@html html_content}{:else}{content}{/if}</pre>
    <!-- eslint-enable svelte/no-at-html-tags -->
  {/if}
  {#if is_overflowing}
    <div class="text-center">
      <button
        type="button"
        class="text-xs font-medium text-gray-500 hover:text-gray-700 underline-offset-2 hover:underline"
        on:click={() => dispatch("see_all")}
      >
        See all
      </button>
    </div>
  {/if}
</div>
