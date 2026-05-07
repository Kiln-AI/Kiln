<script lang="ts">
  import {
    onMount,
    onDestroy,
    afterUpdate,
    createEventDispatcher,
  } from "svelte"

  export let content: string = ""
  export let max_lines: number = 3
  export let text_class: string = "whitespace-pre-wrap break-words"

  let pre_el: HTMLPreElement | undefined
  let is_overflowing = false
  let resize_observer: ResizeObserver | null = null

  const dispatch = createEventDispatcher<{ see_all: void }>()

  function check_overflow() {
    if (!pre_el) return
    // 1px tolerance to avoid sub-pixel rounding flicker
    const overflowing = pre_el.scrollHeight > pre_el.clientHeight + 1
    if (overflowing !== is_overflowing) {
      is_overflowing = overflowing
    }
  }

  afterUpdate(check_overflow)

  onMount(() => {
    if (pre_el) {
      resize_observer = new ResizeObserver(check_overflow)
      resize_observer.observe(pre_el)
    }
  })

  onDestroy(() => {
    resize_observer?.disconnect()
  })
</script>

<div>
  <div class="relative">
    <pre
      bind:this={pre_el}
      class={text_class}
      style="display: -webkit-box; -webkit-line-clamp: {max_lines}; -webkit-box-orient: vertical; overflow: hidden;">{content}</pre>
    {#if is_overflowing}
      <div
        class="pointer-events-none absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-white to-transparent"
      ></div>
    {/if}
  </div>
  {#if is_overflowing}
    <div class="text-center bg-white">
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
