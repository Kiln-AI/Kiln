<script lang="ts">
  import { goto } from "$app/navigation"

  export let label: string
  export let detail: string | undefined = undefined
  export let href: string | undefined = undefined
  export let on_click: (() => void) | undefined = undefined
  export let is_external: boolean = false
  export let status: "warn" | undefined = undefined
  export let is_last: boolean = false

  function clicked() {
    if (on_click) {
      on_click()
    } else if (href) {
      if (is_external) {
        window.open(href, "_blank")
      } else {
        goto(href)
      }
    }
  }
</script>

<button
  type="button"
  on:click={clicked}
  data-testid="settings-row"
  class="flex items-center w-full text-left gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors {is_last
    ? ''
    : 'border-b border-gray-100'}"
>
  <span
    class="flex items-center justify-center w-6 h-6 rounded-[5px] flex-shrink-0 bg-gray-100 text-gray-600"
  >
    <span class="w-3.5 h-3.5 flex items-center justify-center">
      <slot name="icon" />
    </span>
  </span>
  <span class="text-[13px] font-medium text-gray-900 truncate">{label}</span>
  {#if status === "warn"}
    <span
      class="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style="background-color: #F4B544;"
      aria-hidden="true"
    ></span>
  {/if}
  <span class="flex-1"></span>
  {#if detail}
    <span class="text-xs text-gray-500 truncate max-w-[380px] hidden sm:inline">
      {detail}
    </span>
  {/if}
  <span class="text-gray-400 flex-shrink-0 w-3 h-3 flex items-center">
    {#if is_external}
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="w-full h-full"
        aria-hidden="true"
      >
        <path d="M15 3h6v6" />
        <path d="M10 14 21 3" />
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      </svg>
    {:else}
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="w-full h-full"
        aria-hidden="true"
      >
        <path d="m9 6 6 6-6 6" />
      </svg>
    {/if}
  </span>
</button>
