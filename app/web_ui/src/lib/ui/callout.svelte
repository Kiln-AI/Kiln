<script lang="ts">
  // Structured callout — wraps CalloutCard with a fixed title/description/button
  // API. The icon is supplied via the `icon` slot.
  //
  // The action button is optional. Provide either `button_href` (renders an
  // <a>) or `button_onclick` (renders a <button>) along with `button_label`
  // to show it.
  import CalloutCard from "./callout_card.svelte"

  export let title: string
  export let description: string
  export let button_label: string | null = null
  export let button_href: string | null = null
  export let button_onclick: (() => void) | null = null
  export let testid: string | null = null
</script>

<CalloutCard {testid}>
  <slot name="icon" slot="icon" />
  <div class="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
    <div class="flex-grow min-w-0">
      <div class="font-medium text-primary">{title}</div>
      <div class="text-sm font-light text-gray-500">{description}</div>
    </div>
    {#if button_label}
      {#if button_href}
        <a
          href={button_href}
          class="btn btn-primary btn-sm flex-shrink-0 self-start sm:self-auto"
        >
          {button_label}
        </a>
      {:else if button_onclick}
        <button
          type="button"
          class="btn btn-primary btn-sm flex-shrink-0 self-start sm:self-auto"
          on:click={button_onclick}
        >
          {button_label}
        </button>
      {/if}
    {/if}
  </div>
</CalloutCard>
