<script lang="ts">
  import { goto } from "$app/navigation"

  export let name: string
  export let description: string
  export let button_text: string
  export let href: string | undefined = undefined
  export let on_click: (() => void) | undefined = undefined
  export let is_external: boolean = false
  export let badge_text: string | undefined = undefined

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
  on:click={clicked}
  class="group flex items-center justify-between py-4 px-6 rounded-lg hover:bg-gray-50 transition-all duration-200 cursor-pointer w-full text-left"
>
  <div class="flex-1 min-w-0">
    <div class="flex flex-row items-center mb-1">
      <h3 class="text-base font-medium text-gray-900">
        {name}
      </h3>
      {#if badge_text}
        <div class="badge badge-sm ml-2 badge-secondary">
          {badge_text}
        </div>
      {/if}
    </div>

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
