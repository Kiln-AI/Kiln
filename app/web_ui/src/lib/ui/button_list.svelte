<script lang="ts">
  import type { ActionButton } from "$lib/types"

  export let buttons: ActionButton[]

  const getSafeHref = (href: string) => {
    const trimmedHref = href.trim()

    if (
      trimmedHref.startsWith("/") ||
      trimmedHref.startsWith("./") ||
      trimmedHref.startsWith("../") ||
      trimmedHref.startsWith("#")
    ) {
      return trimmedHref
    }

    try {
      const parsedHref = new URL(trimmedHref)

      if (parsedHref.protocol === "http:" || parsedHref.protocol === "https:") {
        return trimmedHref
      }
    } catch {
      return undefined
    }

    return undefined
  }
</script>

<div class="">
  {#each buttons as button}
    {#if button.href}
      <a
        href={getSafeHref(button.href)}
        class="btn {button.primary ? 'btn-primary' : ''} {button.notice
          ? 'btn-warning'
          : ''} w-full mt-4"
        class:btn-disabled={button.disabled}
      >
        {button.label}
      </a>
    {:else}
      <button
        class="btn {button.primary ? 'btn-primary' : ''} {button.notice
          ? 'btn-warning'
          : ''} w-full mt-4"
        class:btn-disabled={button.disabled}
        on:click={button.handler}
        disabled={button.disabled}
      >
        {button.label}
      </button>
    {/if}
  {/each}
</div>
