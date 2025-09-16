<script lang="ts">
  export let name: string
  export let description: string
  export let button_text: string
  export let href: string | undefined = undefined
  export let on_click: (() => void) | undefined = undefined
  export let is_external: boolean = false
</script>

{#if href}
  <a
    {href}
    target={is_external ? "_blank" : null}
    class="group flex items-center justify-between py-4 px-6 rounded-lg hover:bg-gray-50 transition-all duration-200 cursor-pointer"
  >
    <div class="flex-1 min-w-0">
      <h3 class="text-base font-medium text-gray-900 mb-1">
        {name}
      </h3>
      <p class="text-sm font-light text-gray-500 leading-relaxed">
        {description}
      </p>
    </div>

    <div class="flex-shrink-0 ml-6">
      <div
        class="btn btn-mid group-hover:btn-primary transition-colors duration-200"
        style="min-width: 12rem;"
      >
        {button_text}
        {#if is_external}
          <svg
            class="w-3 h-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            ></path>
          </svg>
        {/if}
      </div>
    </div>
  </a>
{:else if on_click}
  <button
    on:click={on_click}
    class="group flex items-center justify-between py-4 px-6 rounded-lg hover:bg-gray-50 transition-all duration-200 cursor-pointer w-full text-left"
  >
    <div class="flex-1 min-w-0">
      <h3 class="text-base font-medium text-gray-900 mb-1">
        {name}
      </h3>
      <p class="text-sm font-light text-gray-500 leading-relaxed">
        {description}
      </p>
    </div>

    <div class="flex-shrink-0 ml-6">
      <div
        class="btn btn-mid group-hover:btn-primary transition-colors duration-200"
        style="min-width: 12rem;"
      >
        {button_text}
      </div>
    </div>
  </button>
{/if}
