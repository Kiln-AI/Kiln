<script lang="ts">
  import { goto } from "$app/navigation"

  export let name: string
  export let description: string
  export let button_text: string
  export let href: string | undefined = undefined
  export let on_click: (() => void) | undefined = undefined
  export let is_external: boolean = false
  export let badge_text: string | undefined = undefined
  export let link_label: string | undefined = undefined
  export let link_href: string | undefined = undefined

  $: has_link = !!(link_label && link_href)

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

  function keydown(event: KeyboardEvent) {
    if (
      event.target === event.currentTarget &&
      (event.key === "Enter" || event.key === " ")
    ) {
      event.preventDefault()
      clicked()
    }
  }
</script>

<!-- A link can't be nested in a <button>, so a row with a link is a div with the button role. -->
<svelte:element
  this={has_link ? "div" : "button"}
  role={has_link ? "button" : undefined}
  tabindex={has_link ? 0 : undefined}
  on:click={clicked}
  on:keydown={has_link ? keydown : undefined}
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
    {#if has_link}
      <a
        href={link_href}
        class="link text-sm font-light text-gray-500 leading-relaxed"
        target="_blank"
        rel="noopener noreferrer"
        on:click|stopPropagation>{link_label}</a
      >
    {/if}
  </div>

  <div class="flex-shrink-0 ml-6">
    <div
      class="btn btn-mid group-hover:btn-primary transition-colors duration-200"
      style="min-width: 12rem;"
    >
      {button_text}
    </div>
  </div>
</svelte:element>
