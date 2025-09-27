<script lang="ts">
  import { onMount, onDestroy } from "svelte"
  import hljs from "highlight.js/lib/core"
  import json from "highlight.js/lib/languages/json"
  hljs.registerLanguage("json", json)

  export let raw_output: string
  export let max_height: string | null = null
  export let hide_toggle: boolean = false

  export let no_padding: boolean = false
  let formatted_json_html: string | null = null
  let is_expanded = false
  let content_element: HTMLElement
  let is_content_overflowing = false
  let resize_observer: ResizeObserver | null = null

  $: {
    try {
      const json_output = JSON.parse(raw_output)
      // Strings are JSON, but not really
      if (typeof json_output !== "string") {
        formatted_json_html = JSON.stringify(json_output, null, 2)
        formatted_json_html = hljs.highlight(formatted_json_html, {
          language: "json",
        }).value
      }
    } catch (e) {
      formatted_json_html = null
    }
  }

  function compute_overflow(
    elem: HTMLElement | undefined,
    maxHeight: string | null,
    expanded: boolean,
  ) {
    if (!elem || !maxHeight || expanded) {
      is_content_overflowing = false
      return
    }

    const temp_element = elem.cloneNode(true) as HTMLElement
    temp_element.style.maxHeight = "none"
    temp_element.style.position = "absolute"
    temp_element.style.visibility = "hidden"
    temp_element.style.pointerEvents = "none"
    // Match current rendered width so wrapping matches the on-screen layout
    temp_element.style.width = `${elem.clientWidth}px`
    document.body.appendChild(temp_element)

    const natural_height = temp_element.scrollHeight
    document.body.removeChild(temp_element)

    const max_height_px = parseInt(maxHeight.replace("px", ""))
    is_content_overflowing = natural_height > max_height_px
  }

  // Recompute when inputs change
  $: compute_overflow(content_element, max_height, is_expanded)

  onMount(() => {
    if (content_element) {
      // scenario where this matters: content initially fits when the container is at full width,
      // but on smaller viewport, the container is narrower and the content now overflows
      resize_observer = new ResizeObserver(() => {
        compute_overflow(content_element, max_height, is_expanded)
      })
      resize_observer.observe(content_element)
    }
  })

  onDestroy(() => {
    resize_observer?.disconnect()
  })

  function copy_to_clipboard() {
    navigator.clipboard.writeText(raw_output)
  }

  function toggle_expansion() {
    is_expanded = !is_expanded
  }
</script>

<head>
  <link rel="stylesheet" href="/styles/highlightjs.min.css" />
</head>

<div class="relative">
  <div
    class="flex flex-row gap-2 bg-base-200 p-1 rounded-lg {no_padding
      ? ''
      : 'p-1'} {max_height && !is_expanded ? 'overflow-hidden' : ''}"
    style={max_height && !is_expanded ? `max-height: ${max_height}` : ""}
  >
    <!-- eslint-disable svelte/no-at-html-tags -->
    <pre
      bind:this={content_element}
      class="grow p-3 whitespace-pre-wrap text-xs min-w-0 {no_padding
        ? ''
        : 'p-3'}"
      style="overflow-wrap: anywhere;">{#if formatted_json_html}{@html formatted_json_html}{:else}{raw_output}{/if}</pre>
    <!-- eslint-enable svelte/no-at-html-tags -->
    <div class="flex-none">
      <button
        on:click|stopPropagation={copy_to_clipboard}
        class="btn btn-sm btn-square h-8 w-8 shadow-none text-gray-400 hover:text-gray-900"
      >
        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
        <svg
          class="w-5 h-5 p-0"
          viewBox="0 0 64 64"
          xmlns="http://www.w3.org/2000/svg"
          stroke-width="3"
          stroke="currentColor"
          fill="none"
        >
          <rect x="11.13" y="17.72" width="33.92" height="36.85" rx="2.5" />
          <path
            d="M19.35,14.23V13.09a3.51,3.51,0,0,1,3.33-3.66H49.54a3.51,3.51,0,0,1,3.33,3.66V42.62a3.51,3.51,0,0,1-3.33,3.66H48.39"
          />
        </svg>
      </button>
    </div>
  </div>

  <!-- Toggle bar with gradient - only show when content overflows -->
  {#if max_height && is_content_overflowing && !is_expanded}
    <div
      class="absolute bottom-0 left-0 right-0 flex items-end justify-center pb-2 bg-gradient-to-t from-base-200 via-base-200/80 to-transparent h-12 pointer-events-none"
    >
      <button
        on:click={toggle_expansion}
        class="btn btn-sm btn-outline pointer-events-auto bg-base-200 {hide_toggle
          ? 'hidden'
          : ''}"
      >
        Show All
      </button>
    </div>
  {/if}

  <!-- Hide toggle when expanded -->
  {#if max_height && is_expanded && !hide_toggle}
    <div class="flex justify-center pt-2">
      <button on:click={toggle_expansion} class="btn btn-sm btn-outline">
        Collapse
      </button>
    </div>
  {/if}
</div>
